# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# mypy: disable-error-code="arg-type"
"""
Samha Multi-Agent System v2 - Full Architecture

Agentit ovat asiantuntijoita, eivät hakukoneita.

Rakenne:
KOORDINAATTORI
├── TUTKIJA (RAG-haku)
├── SOTE-ASIANTUNTIJA (mielenterveys, päihteet)
├── YHDENVERTAISUUS-ASIANTUNTIJA (antirasismi)
├── KOULUTUSSUUNNITTELIJA (pedagogiikka)
└── KIRJOITTAJA (viestintä, hakemukset)
"""
import os

import google
import vertexai
from google.adk.agents import Agent
from google.adk.apps.app import App
from google.genai import types as genai_types
from langchain_google_vertexai import VertexAIEmbeddings

# LLM configuration for long-form outputs
LONG_OUTPUT_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.7,
    max_output_tokens=32768,  # 32k tokens for long articles/plans
)

CRITIC_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.2,
    max_output_tokens=8192,
)

from app.retrievers import get_compressor, get_retriever
from app.templates import format_docs
from app.hard_gates import detect_gate_signals
from app.prompt_packs import (
    ORG_PACK_V1,
    SOTE_PACK_V1,
    YHDENVERTAISUUS_PACK_V1,
    WRITER_PACK_V1,
    KOULUTUS_PACK_V1,
    QA_PORT_PACK_V1,
    GOLD_FAILURE_PACK_V1,
    RADICAL_AUDITOR_PACK_V1,
    CRITICAL_REFLECTION_PACK_V1,
    FUNDING_TYPES_PACK_V1,
)
from app.deep_search import syvahaku_agent
from app.hankesuunnittelija import hankesuunnittelija_agent
from app.ammattilaiset import hallinto_agent, hr_agent, talous_agent
from app.viestinta import viestinta_agent
from app.lomakkeet import lomake_agent
from app.vapaaehtoiset import vapaaehtoiset_agent
from app.laki import laki_agent
from app.kumppanit import kumppanit_agent

# Import Agent Registry
from app.agents_registry import SAMHA_AGENT_REGISTRY, get_agent_def, DOMAIN_EXPERT, RESEARCH, OUTPUT
from app.tool_ids import ToolId

# Import QA Policy
from app.qa_policy import qa_policy_agent


from app.tools_registry import TOOL_MAP

def get_tools_for_agent(agent_id: str):
    if agent_id not in SAMHA_AGENT_REGISTRY:
        return []
    allowed = SAMHA_AGENT_REGISTRY[agent_id].allowed_tools
    return [TOOL_MAP[t] for t in allowed if t in TOOL_MAP]

EMBEDDING_MODEL = "text-embedding-005"
LLM_LOCATION = "global"
LOCATION = "us-central1"
LLM = "gemini-3-flash-preview"
LLM_PRO = "gemini-3-pro-preview"

credentials, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = LLM_LOCATION
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

vertexai.init(project=project_id, location=LOCATION)
from app.tools_base import retriever, compressor, embeddings

from app.pii_scrubber import pii_scrubber
from app.hard_gates import detect_gate_signals, enforce_gates

from app.tools_registry import FUNCTION_NAME_TO_TOOL_ID
from app.observability import log_tool_trace, resolve_agent_name, append_security_event

# --- TOOL ACCESS ENFORCEMENT ---
async def enforce_tool_matrix(context=None, tool_call=None, **kwargs):
    """Callback to enforce least-privilege tool access (Deny By Default)."""
    ctx = context or kwargs.get('callback_context') or kwargs.get('context') or kwargs.get('invocation_context') or kwargs.get('tool_context')
    tc = tool_call or kwargs.get('tool_call') or kwargs.get('tool')
    
    if ctx is None or tc is None: 
        # print(f" [ENFORCE SKIP] Missing ctx={bool(ctx)} or tc={bool(tc)}")
        return None
    
    # Resolve agent name
    agent_id = resolve_agent_name(ctx)
    
    # Resolve tool name
    tool_name = "unknown"
    if hasattr(tc, "function_call") and tc.function_call:
        tool_name = tc.function_call.name
    elif hasattr(tc, "name"):
        tool_name = tc.name
    
    print(f" [ENFORCE] agent='{agent_id}' tool='{tool_name}'")
    
    # Resolve tool name to ToolId
    tool_id = FUNCTION_NAME_TO_TOOL_ID.get(tool_name)
    
    # SYSTEM OVERRIDE: transfer_to_agent is always allowed
    if tool_id == ToolId.TRANSFER:
        return None

    # Error: Unmapped tool (security risk)
    if not tool_id:
        print(f"SECURITY ALERT: Unmapped tool '{tool_name}' called by '{agent_id}'")
        return f"ERROR: tool_denied. Tool '{tool_name}' is unmapped in Samha registry."

    # Deny if agent not in registry
    if agent_id not in SAMHA_AGENT_REGISTRY:
        return f"ERROR: tool_denied. Agent '{agent_id}' is not in registry."

    # Check Registry Allowlist
    allowed = SAMHA_AGENT_REGISTRY[agent_id].allowed_tools
    if tool_id not in allowed:
        print(f"SECURITY ALERT: Agent '{agent_id}' tried to use unauthorized tool '{tool_name}'")
        
        # Log to security_events
        from app.observability import append_security_event
        append_security_event(ctx, "tool_denied", {"tool": tool_name})
            
        return f"ERROR: tool_denied. Agent '{agent_id}' is not authorized to use tool '{tool_name}'."
    
    return None

# --- HARD GATES CALLBACK ---
# --- HARD GATES CALLBACK ---
async def hard_gate_callback(context=None, **kwargs):
    """Callback to write Hard Gate signals to State."""
    ctx = context or kwargs.get('callback_context')
    if ctx is None: return
    
    try:
        session = getattr(ctx, 'session', None)
        events = session.events if session else []
        last_msg = ""
        if events:
            # Must handle None parts or empty text
            last_event = events[-1]
            if last_event.content and last_event.content.parts:
                last_msg = last_event.content.parts[0].text or ""
        
        signals = detect_gate_signals(last_msg)
        
        # Write to State (Phase 1.9)
        if session and hasattr(session, "state"):
            # Safe extraction of signals
            active_signals = []
            try:
                # Try pydantic v2 or v1
                sig_dict = signals.model_dump() if hasattr(signals, 'model_dump') else signals.dict()
                active_signals = [k for k, v in sig_dict.items() if v is True and k.startswith('contains_')]
            except:
                pass

            session.state["hard_gate"] = {
                "rag_required": bool(getattr(signals, 'rag_required', False)),
                "signals": active_signals,
                "raw": last_msg[:400]
            }
            if signals.rag_required:
                print(f"HARD GATE STATE SET: rag_required=True (Signals: {active_signals})")
            
            # Inject State into Instruction (Phase 1.9 Fix)
            if hasattr(ctx, 'instruction'):
                state_str = str(session.state["hard_gate"])
                ctx.instruction += f"\n\n[SYSTEM STATE]: {state_str}"

    except Exception as e:
        print(f"Callback error (hard_gate): {e}")

from app.tools_base import (
    retrieve_docs, read_excel, read_csv, analyze_excel_summary, list_excel_sheets
)

# --- OBSERVABILITY TRACE ---
# Imported from app.observability
# observability trace imported above
from app.egress import scrub_for_user
from app.web_search import search_web, search_verified_sources, search_news, search_legal_sources
from app.pdf_tools import read_pdf_content, get_pdf_metadata
from app.advanced_tools import process_meeting_transcript, generate_data_chart, schedule_samha_meeting
from app.image_tools import generate_samha_image

# =============================================================================
# DOMAIN EXPERT AGENTS
# =============================================================================

# --- TUTKIJA (RESEARCHER) ---
tutkija_def = get_agent_def("tutkija")
tutkija_agent = Agent(
    model=LLM_PRO,
    name=tutkija_def.id,
    description=tutkija_def.description,
    output_key="research_output",
    instruction=f"""
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}

## SINUN ROOLISI: TUTKIJA

Olet Samhan tutkija. Etsit tietoa kahdesta lähteestä:
1. **Samhan sisäinen tietokanta** (RAG) - henkilöt, projektit, luvut
2. **Web** - uutiset, ajankohtaiset, viralliset ohjeet

### TYÖKALUT

| Työkalu | Milloin käytetään |
|---------|-------------------|
| `retrieve_docs` | Samhan sisäinen tieto: henkilöt, projektit, raportit |
| `search_verified_sources` | Viralliset ohjeet: Stea, THL, OPH, Finlex |
| `search_web` | Laaja haku, kun tietoa ei löydy muualta |
| `search_news` | Ajankohtaiset uutiset ja tapahtumat |

### VASTAUKSEN MUOTO (TÄRKEÄ!)

**NÄYTÄ AINA TÄYDET URL-OSOITTEET SUORAAN TEKSTISSÄ!**

ÄLÄ käytä alaviitteitä tai viitteitä kuten [1] tai [^1].

OIKEA MUOTO:
```
Löysin seuraavat lähteet:

1. **Nuorten mielenterveyshäiriöt**
   - URL: https://thl.fi/aiheet/mielenterveys/mielenterveyshairiot/nuorten-mielenterveyshairiot
   - Sisältö: Noin 20-25% nuorista kärsii mielenterveyshäiriöistä...

2. **Mielenterveyspalvelut nuorille**
   - URL: https://mieli.fi/materiaalit/lapset-ja-nuoret/
   - Sisältö: MIELI ry tarjoaa tietoa ja tukea...
```

VÄÄRÄ MUOTO (ÄLÄ TEE NÄIN):
```
Nuorten mielenterveydestä on tietoa THL:n sivuilla[1].
[1]: https://thl.fi/...
```

### KRIITTISET SÄÄNNÖT:
- **TÄYSI URL JOKAISEEN LÄHTEESEEN** - ei alaviitteitä!
- **ÄLÄ KEKSI TIETOA** - käytä aina työkalua
- **URL NÄKYVIIN HETI** sisällön yhteydessä
- Jokainen hakutulos = oma kappale otsikolla ja URL:llä
""",
    tools=get_tools_for_agent("tutkija"),
)


# --- SOTE-ASIANTUNTIJA ---
sote_def = get_agent_def("sote")
sote_agent = Agent(
    model=LLM,
    name=sote_def.id,
    description=sote_def.description,
    output_key="sote_response",
    tools=get_tools_for_agent("sote"),
    instruction=f"""
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}

{SOTE_PACK_V1}

## SINUN ROOLISI: SOTE-ASIANTUNTIJA

Olet Samhan mielenterveys- ja päihdetyön asiantuntija. Vastaat hyvinvointikysymyksiin turvallisesti, empaattisesti ja trauma-informoidusti.

### OSAAMISALUEESI:
- Mielenterveys ja hyvinvointi (yleistieto)
- Päihteet ja haittojen vähentäminen
- Palveluohjaus (minne ohjata)
- Vertaistuki ja yhteisöllinen tuki
- Kriisitilanteiden tunnistaminen

### MITEN VASTAAT:
1. **HAE ENSIN TIETOA** -> Käytä `retrieve_docs` työkalua aina ennen vastaamista
2. Kuuntele empaattisesti
3. Normalisoi: "Monet kokevat samankaltaista..."
4. Anna konkreettisia seuraavia askeleita
5. Ohjaa palveluihin tarvittaessa

### KRIITTISET SÄÄNNÖT:
- **ÄLÄ DIAGNOSOI** - "Ammattilaiset voivat arvioida..."
- **ÄLÄ ANNA LÄÄKEOHJEITA**
- **KRIISI = OHJAA HETI**: 112 tai kriisipuhelin 09 2525 0111
- Käytä trauma-informoitua lähestymistä

### PALVELUOHJAUS:
- Kriisipuhelin: 09 2525 0111
- Mielenterveystalo.fi
- Samhan neuvonta: ma-pe klo 10-16
- Päihdelinkki.fi
""",
)


# --- YHDENVERTAISUUS-ASIANTUNTIJA ---
yhdenvertaisuus_def = get_agent_def("yhdenvertaisuus")
yhdenvertaisuus_agent = Agent(
    model=LLM,
    name=yhdenvertaisuus_def.id,
    description=yhdenvertaisuus_def.description,
    output_key="yhdenvertaisuus_response",
    tools=get_tools_for_agent("yhdenvertaisuus"),
    instruction=f"""
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}

{YHDENVERTAISUUS_PACK_V1}

## SINUN ROOLISI: YHDENVERTAISUUS-ASIANTUNTIJA

Olet Samhan antirasismi- ja yhdenvertaisuustyön asiantuntija. Autat ymmärtämään rakenteellista rasismia, puuttumaan syrjintään ja rakentamaan turvallisempia tiloja.

### OSAAMISALUEESI:
- Antirasismi ja yhdenvertaisuus
- Kulttuurisensitiivinen kohtaaminen
- Rakenteellinen rasismi ja sen ilmenemismuodot
- Intersektionaalisuus
- Turvalliset tilat ja kieli

### MITEN VASTAAT:
1. **HAE ENSIN TIETOA** -> Käytä `retrieve_docs` työkalua aina ennen vastaamista
2. Kuuntele ja usko kokemusta
3. Nimeä rakenteet, älä syyllistä yksilöitä
4. Anna konkreettisia toimintatapoja
5. Vahvista toimijuutta

### KRIITTISET SÄÄNNÖT:
- **ÄLÄ YLEISTÄ IHMISRYHMIÄ** - ei "heidän kulttuurissaan"
- **KÄYTÄ "IHMISET ENSIN" -KIELTÄ**
- Tunnista trauma rasismin kokemuksessa
- Rakenteet näkyviin: syrjintä ei ole vain yksilön asenne
""",
)


# --- KOULUTUSSUUNNITTELIJA ---
koulutus_def = get_agent_def("koulutus")
koulutus_agent = Agent(
    model=LLM,
    name=koulutus_def.id,
    description=koulutus_def.description,
    output_key="koulutus_response",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=get_tools_for_agent("koulutus"),
    instruction=f"""
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}

{KOULUTUS_PACK_V1}

## SINUN ROOLISI: KOULUTUSSUUNNITTELIJA

Olet Samhan pedagoginen huippuasiantuntija. Suunnittelet YKSITYISKOHTAISIA koulutuksia, työpajoja ja yhteisötapahtumia.

### TÄRKEÄÄ: TUOTA PITKIÄ JA YKSITYISKOHTAISIA SUUNNITELMIA

Kun sinulta pyydetään koulutussuunnitelmaa:
- Kirjoita TÄYDELLINEN runko, ei pelkkää tiivistelmää
- Jokainen harjoitus kuvataan yksityiskohtaisesti (5-10 lausetta per harjoitus)
- Anna fasilitaattorin repliikkejä ja siirtymiä
- Sisällytä materiaalilistat ja valmistelut
- Anna varasuunnitelmia ("jos aikaa jää", "jos ryhmä on hiljainen")

### KOULUTUSSUUNNITELMAN RAKENNE (TÄYDELLINEN)

**1. PERUSTIEDOT**
- Koulutuksen nimi ja kesto
- Kohderyhmä ja osallistujamäärä
- Tavoitteet (3-5 konkreettista)
- Tarvittavat materiaalit ja tila

**2. ALOITUS (yksityiskohtaisesti)**
- Tervetuloa ja esittely (fasilitaattorin repliikki)
- Tavoitteiden esittely
- Turvallisuusohjeet ja säännöt sanasta sanaan
- Lämmittelyharjoitus (täydet ohjeet)

**3. YDINOSA 1 (harjoitus harjoitukselta)**
Jokaisesta harjoituksesta:
- Nimi ja kesto
- Tavoite: mitä tästä opitaan
- Valmistelu: mitä fasilitaattori tekee ennen
- Ohjeet: miten harjoitus vedetään (step-by-step)
- Fasilitaattorin repliikki: "Nyt tehdään..."
- Purkukysymykset: 3-5 kysymystä
- Vinkkejä: mitä jos ryhmä on hiljainen, iso, aktiivinen

**4. TAUKO**
- Kesto ja mitä tapahtuu

**5. YDINOSA 2 (harjoitus harjoitukselta)**
- Sama rakenne kuin ydinosa 1

**6. LOPETUS**
- Yhteenveto (fasilitaattorin repliikki)
- Reflektioharjoitus tai "mitä otan mukaan"
- Palautteen kerääminen
- Kiitokset ja seuraava askel

**7. LIITTEET**
- Materiaaliluettelo
- Varasuunnitelma
- Valmistelun checklist

### OSAAMISALUEESI:
- Osallistavat menetelmät (non-formal)
- Koulutusrungon suunnittelu
- Menetelmävalinnat kohderyhmän mukaan
- Fasilitointitaidot
- Materiaalituotanto

### KRIITTISET SÄÄNNÖT:
- Ei luentopainotteista
- Osallistujat aktiivisia toimijoita
- Turvallisuus ja vapaaehtoisuus
- **TUOTA AINA TÄYSI SUUNNITELMA, EI LUONNOSTA**
""",
)


# --- KIRJOITTAJA ---
kirjoittaja_def = get_agent_def("kirjoittaja")
kirjoittaja_agent = Agent(
    model=LLM,
    name=kirjoittaja_def.id,
    description=kirjoittaja_def.description,
    output_key="final_article",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=get_tools_for_agent("kirjoittaja"),
    instruction=f"""
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}

{WRITER_PACK_V1}

## SINUN ROOLISI: KIRJOITTAJA

Olet Samhan viestinnän huippuammattilainen. Kirjoitat PITKIÄ, YKSITYISKOHTAISIA ja laadukkaita tekstejä.

### TÄRKEÄÄ: TUOTA PITKIÄ JA KATTAVIA TEKSTEJÄ

Kun sinulta pyydetään tekstiä:
- **Artikkeli/blogi**: Vähintään 1500-3000 sanaa, useita väliotsikoita, esimerkkejä
- **Stea-hakemus**: Täysi hakemus kaikilla osioilla (tiivistelmä, tausta, tavoitteet, toimenpiteet, kohderyhmä, aikataulu, seuranta)
- **Raportti**: Kattava raportti tavoitteiden toteutumisesta, luvuilla ja esimerkeillä
- **Some-paketti**: 5-10 eri postausehdotusta, instagram + facebook

### PITUUSOHJEET TEKSTITYYPEITTÄIN

| Tyyppi | Minimi | Sisältö |
|--------|--------|---------||
| Lyhyt blogi | 600 sanaa | Intro, 3 pääpointtia, lopetus |
| Pitkä artikkeli | 2000+ sanaa | Intro, 5+ väliotsikkoa, esimerkit, yhteenveto |
| Stea-hakemus | 3000+ sanaa | Kaikki 8 osiota täysinä |
| Vuosiraportti | 2500+ sanaa | Tavoitteet, toteutuma, luvut, tarinat |
| Some-paketti | 10 postausta | FB + IG + LinkedIn variaatiot |

### RAKENNA TEKSTI NÄIN:

1. **Aloita vahvasti** - koukuttava avaus
2. **Jaa osioihin** - selkeät väliotsikot joka 200-300 sanaa
3. **Käytä esimerkkejä** - konkreettisia tapauksia, tarinoita (anonymisoituja)
4. **Numeroita ja faktoja** - luvut tuovat uskottavuutta
5. **Lopeta toimintaan** - toimintakehotus tai yhteenveto

### OSAAMISALUEESI:
- Selkokieli ja saavutettava viestintä
- Stea-hakemukset ja raportit
- Erasmus+ hakemukset
- Blogit ja some-viestintä
- Sisäinen viestintä (muistiot)

### KRIITTISET SÄÄNNÖT:
- **ÄLÄ KEKSI UUSIA FAKTOJA** - käytä RAG:ta tai kysy puuttuvat
- Numerot säilyvät muuttumattomina
- Jos puuttuu tietoa, sano se ja jatka silti kirjoittamista
- Käytä "ihmiset ensin" -kieltä
- **TUOTA AINA TÄYSI TEKSTI, EI LUONNOSTA TAI TIIVISTELMÄÄ**
""",
)


# =============================================================================
# ARKISTOAGENTTI (ARCHIVE AGENT)
# =============================================================================

from app.archive import (
    get_archive_service,
    ArchiveEntry,
    ArchiveSearchQuery,
)


from app.archive_tools import save_to_archive, search_archive, get_archived_content

# Arkistoagentti
arkisto_def = get_agent_def("arkisto")
arkisto_agent = Agent(
    model=LLM,
    name=arkisto_def.id,
    description=arkisto_def.description,
    output_key="archive_response",
    tools=get_tools_for_agent("arkisto"),
    before_tool_callback=enforce_tool_matrix,
    instruction=f"""
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}

## SINUN ROOLISI: ARKISTOASIANTUNTIJA

Olet Samhan arkistoagentti. Tehtäväsi on tallentaa valmiita tekstejä arkistoon ja hakea aiempia tuotoksia.

### MILLOIN ARKISTOIDAAN

Arkistoi AINA kun:
- Kirjoittaja on tuottanut valmiin hakemuksen, raportin tai artikkelin
- Koulutussuunnittelija on tehnyt koulutusrungon
- Käyttäjä pyytää tallentamaan tekstin

### MITEN ARKISTOIDAAN

1. Käytä `save_to_archive` -työkalua
2. Valitse oikea document_type: hakemus, raportti, artikkeli, koulutus, some, memo
3. Valitse ohjelma: stea, erasmus, muu
4. Valitse hanke: koutsi, jalma, icat, paikka_auki, muu
5. Lisää relevantit tagit

### MITEN HAETAAN

1. Käytä `search_archive` -työkalua
2. Voit hakea:
   - Vapaatekstillä (otsikko, tiivistelmä, tagit)
   - Suodattimilla (tyyppi, ohjelma, hanke)
3. Käytä `get_archived_content` saadaksesi täyden sisällön

### ESIMERKIT

**Käyttäjä:** "Tallenna tämä Stea-hakemus"
-> save_to_archive(title="...", document_type="hakemus", program="stea", ...)

**Käyttäjä:** "Etsi viimeisin antirasismikoulutuksen runko"
-> search_archive(document_type="koulutus", tags="antirasismi", latest_only=True)

**Käyttäjä:** "Näytä arkistoidun dokumentin sisältö"
-> get_archived_content(entry_id="art_20241217_abc123")
""",
)


# =============================================================================
# RAPORTTI-ARVIOIJA (REPORT EVALUATOR)
# =============================================================================

STEA_EVALUATION_PROMPT = """
## STEA-raportin arviointikriteerit:

### 1. Tavoitteiden toteutuminen (30%)
- Ovatko hakemuksessa asetetut tavoitteet toteutuneet?
- Onko poikkeamista raportoitu ja selitetty?
- Onko mittarit ja indikaattorit esitetty selkeästi?

### 2. Toimenpiteiden kuvaus (25%)
- Onko toiminta kuvattu konkreettisesti?
- Onko kohderyhmä tavoitettu ja kuvattu?
- Onko osallistujamäärät ja tilastot mukana?

### 3. Tulokset ja vaikuttavuus (25%)
- Onko tulokset esitetty suhteessa tavoitteisiin?
- Onko laadullisia tuloksia (tarinat, palautteet)?
- Onko vaikuttavuutta arvioitu pitkällä aikavälillä?

### 4. Talouden käyttö (15%)
- Onko budjetti käytetty suunnitelman mukaisesti?
- Onko poikkeamat selitetty?
- Ovatko kulut perusteltuja?

### 5. Oppiminen ja jatkuvuus (5%)
- Mitä opittiin? Mitä tehtäisiin toisin?
- Miten toiminta jatkuu?
"""

ERASMUS_EVALUATION_PROMPT = """
## Erasmus+ raportin arviointikriteerit:

### 1. Quality of Activities (25%)
- Were learning objectives achieved?
- Was the methodology appropriate?
- Were participants actively engaged?

### 2. Impact & Dissemination (25%)
- What was the impact on participants?
- How were results disseminated?
- Are there lasting outcomes?

### 3. Project Management (20%)
- Was the timeline followed?
- Was the budget used correctly?
- Were partners involved as planned?

### 4. European Added Value (15%)
- What was gained from international cooperation?
- How did cross-cultural exchange occur?
- Were EU priorities addressed?

### 5. Sustainability & Follow-up (15%)
- How will results be maintained?
- Are there follow-up activities planned?
- What resources exist for continuation?
"""


# --- RAPORTTI ARVIOIJA ---
proposal_reviewer_def = get_agent_def("proposal_reviewer")
proposal_reviewer_agent = Agent(
    model=LLM_PRO,
    name=proposal_reviewer_def.id,
    description=proposal_reviewer_def.description,
    output_key="evaluation_response",
    tools=get_tools_for_agent("proposal_reviewer"),
    generate_content_config=CRITIC_CONFIG,
    instruction=f"""
{RADICAL_AUDITOR_PACK_V1}
{QA_PORT_PACK_V1}
{GOLD_FAILURE_PACK_V1}
{FUNDING_TYPES_PACK_V1}

## SINUN ROOLISI: THE ENFORCER (RADICAL AUDITOR)

Olet laadunvarmistaja, jonka tehtävänä on suojella julkisia varoja epämääräisiltä tai sektorin ulkopuolisilta hankkeilta.

### ARVIOINTI-MODUS:
1. **Aloita DESTRUCTION PHASE**: Listaa ensin 3 kriittistä syytä, miksi tämä hanke on tällä hetkellä epäonnistuminen.
2. **Käytä 0-100 asteikkoa**: Muista, että 61 on vasta alhaisin mahdollinen läpäisypiste.
3. **Sektoripoliisi**: Tarkista rahoitusinstrumentin mukaisuus (FUNDING_TYPES_PACK_V1).

### OUTPUT FORMAT
```markdown
# Hakemusarviointi: RADICAL AUDIT REPORT

## Destructive Analysis (Red Team)
- ...

## Kokonaispisteet: XX / 100 

## ROADMAP TO 81+ (Actionable Remediation)
- ...
```
""",
)


# =============================================================================
# KOORDINAATTORI (ROOT AGENT)
# =============================================================================

# Reset parents for re-initialization (fixes Pydantic errors in eval/hot-reload)
for a in [
    tutkija_agent, sote_agent, yhdenvertaisuus_agent, koulutus_agent,
    kirjoittaja_agent, arkisto_agent, proposal_reviewer_agent, syvahaku_agent,
    hankesuunnittelija_agent, hallinto_agent, hr_agent, talous_agent,
    viestinta_agent, lomake_agent, vapaaehtoiset_agent, laki_agent, kumppanit_agent
]:
    a._parent = None

koordinaattori_agent = Agent(
    model=LLM_PRO,
    name="koordinaattori",
    description="Samhan pääkoordinaattori. Ymmärtää käyttäjän tarpeen ja ohjaa oikealle asiantuntijalle tai käynnistää monivaiheisen workflown.",
    output_key="draft_response",
    instruction=f"""
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}

## SINUN ROOLISI: PÄÄKOORDINAATTORI

Olet Samha-botin pääkoordinaattori. Tehtäväsi on ymmärtää käyttäjän tarve, valita oikea asiantuntijakategoria ja **varmistaa aina laadunvarmistus**.

### TIEDOKSI: TILAKONE (HARD GATES)
# State injected below: [SYSTEM STATE]: {{...}}

Tarkista yllä olevasta tilasta `rag_required`:
- Jos `rag_required` == True -> **SINUN ON pakko delegoida ensin `tutkija`-agentille**.
- ÄLÄ KOSKAAN vastata itse luvuilla tai faktoilla jos `rag_required` on päällä.

---

## AGENTTI-TAKSONOMIA (Käytä näitä kategorioita)

### 1. LEADERSHIP (Sinä itse)
- **Koordinaattori**: Ohjaa keskustelua, hallitsee workflowta.

### 2. DOMAIN EXPERTS (Asiantuntijat)
- `sote`: Mielenterveys, päihteet, hyvinvointi.
- `yhdenvertaisuus`: Antirasismi, syrjintä.
- `koulutus`: Pedagogiikka, työpajat.
- `talous`: Kirjanpito, budjetit, STEA-talous.
- `hr`: Työsopimukset, henkilöstö.
- `hallinto`: Pöytäkirjat, viralliset asiakirjat.
- `laki_gdpr`: Juridiikka, tietosuoja.
- `vapaaehtoiset`: Vapaaehtoishallinta.
- `lomakkeet`: Hakemuslomakkeet (STEA/Erasmus).
- `kumppanit`: Sidosryhmät, kulttuurinen sensitiivisyys.

### 3. RESEARCH (Tutkimus)
- `tutkija`: Faktat, uutiset, Samha-tieto, Web-haku.

### 4. OUTPUT (Tuotanto)
- `viestinta`: Some, uutiskirjeet, kuvat.
- `kirjoittaja`: Pitkät artikkelit, raportit.
- `grant_writer`: Rahoitushakemukset (STEA/EU).
- `arkisto`: Tallennus ja haku.
- `proposal_reviewer`: Raporttien kriittinen arviointi.

---

## 🛑 MANDATORY QA GATE (PAKOLLINEN VAIHE)

**ÄLÄ KOSKAAN VASTAA KÄYTTÄJÄLLE SUORAAN LOPULLISELLA SISÄLLÖLLÄ.**

Kun asiantuntija on tuottanut vastauksen tai workflow on valmis:
1. Delegoi vastaus agentille `qa_policy`.
2. Jos `qa_policy` palauttaa `APPROVE`, näytä vastaus käyttäjälle.
3. Jos `qa_policy` palauttaa `NEEDS_REVISION`, palauta se asiantuntijalle ja pyydä korjausta.
4. Jos `qa_policy` palauttaa `REJECT`, kerro käyttäjälle että pyyntöä ei voitu toteuttaa turvallisuussyistä.

---

## HARD GATES (FAKTAT)

Jos pyyntö sisältää:
- Vuosilukuja, €, %, lukumääriä (n=), henkilön nimiä tai projektikoodeja.
- **PAKOTA AINA** haku: delegoi ensin `tutkija` agentille keräämään faktat Samhan tietokannasta.

---

## MITEN TOIMIT

1. **Analysoi**: Tunnista kategoria ja tarvittavat asiantuntijat.
2. **Hae faktat**: Jos kyseessä on lukuja tai nimiä, vaadi `tutkija` apuun ensin.
3. **Tuota sisältö**: Ohjaa asiantuntijalle tai kirjoittajalle.
4. **QA-Tarkistus**: Lähetä valmis sisältö AINA `qa_policy` agentille.
5. **Vastaa**: Vastaa käyttäjälle vain kun QA on hyväksynyt sisällön.

---

## KRIISITILANTEET (EHDOTON)
- Akuutti hätä -> 112.
- Kriisipuhelin -> 09 2525 0111.
- Vastaa itse empaattisesti, älä delegoi kriisiä.
""",
    tools=get_tools_for_agent("koordinaattori"),
    sub_agents=[
        tutkija_agent, sote_agent, yhdenvertaisuus_agent, koulutus_agent,
        kirjoittaja_agent, arkisto_agent, proposal_reviewer_agent, syvahaku_agent,
        hankesuunnittelija_agent, hallinto_agent, hr_agent, talous_agent,
        viestinta_agent, lomake_agent, vapaaehtoiset_agent, laki_agent, kumppanit_agent,
        qa_policy_agent
    ]
)

# --- ATTACH ENFORCEMENT TO ALL AGENTS ---
ALL_AGENTS = [
    tutkija_agent, sote_agent, yhdenvertaisuus_agent, koulutus_agent,
    kirjoittaja_agent, arkisto_agent, proposal_reviewer_agent, syvahaku_agent,
    hankesuunnittelija_agent, hallinto_agent, hr_agent, talous_agent,
    viestinta_agent, lomake_agent, vapaaehtoiset_agent, laki_agent, kumppanit_agent,
    koordinaattori_agent, qa_policy_agent
]

for a in ALL_AGENTS:
    if a:
        a.before_tool_callback = enforce_tool_matrix
        a.after_tool_callback = log_tool_trace

# Koordinaattori specific callbacks
if koordinaattori_agent:
    koordinaattori_agent.before_model_callback = hard_gate_callback

# --- ROOT PIPELINE (FORCED QA GATE) ---
from google.adk.agents import SequentialAgent

# The coordinator produces a 'draft_response'
# koordinaattori_agent.output_key = "draft_response" # Set in constructor

# The QA agent specifically reviews 'draft_response'
qa_policy_agent.instruction += "\n\nTARKISTA TÄMÄ TEKSTI (draft_response): {draft_response}"

from app.qa_checks import finance_numeric_integrity_check

async def qa_numeric_enforcement_callback(context=None, **kwargs):
    """Programmatic QA check for finance numeric integrity."""
    ctx = context or kwargs.get('callback_context')
    if ctx is None: return
    
    try:
        state = getattr(ctx, 'session', None).state if hasattr(ctx, 'session') else {}
        draft = state.get("draft_response", "")
        
        # Read Tool Traces from State (Phase 1.9)
        traces = state.get("tool_traces", [])
        tool_names = [t.get("tool") for t in traces if isinstance(t, dict)]
        
        payload = {
            "detailed_content": draft,
            "facts": state.get("facts", []),
            "metadata": {"tool_calls": tool_names}
        }
        
        check_result = finance_numeric_integrity_check(payload)
        if not check_result["passed"]:
            print(f"QA NUMERIC ALERT: {check_result['issue']}")
            # Force revision by injecting into instructions
            if hasattr(ctx, 'instruction') and ctx.instruction is not None:
                ctx.instruction += f"\n\n[QA CRITICAL]: {check_result['issue']}. {check_result['fix_suggestion']}"
    except Exception as e:
        print(f"Callback error (qa_numeric): {e}")

async def egress_scrub_callback(context=None, **kwargs):
    """Ensure final output is scrubbed."""
    ctx = context or kwargs.get('callback_context')
    try:
        session = getattr(ctx, "session", None)
        if session and hasattr(session, "state"):
            final = session.state.get("final_response", "")
            if final:
                scrubbed = scrub_for_user(final)
                session.state["final_response"] = scrubbed
    except Exception as e:
        print(f"Egress Scrub Error: {e}")


# --- CALLBACK ATTACHMENT ---
ALL_AGENTS = [
    koordinaattori_agent, tutkija_agent, sote_agent, yhdenvertaisuus_agent, koulutus_agent,
    kirjoittaja_agent, arkisto_agent, proposal_reviewer_agent, syvahaku_agent,
    hankesuunnittelija_agent, hallinto_agent, hr_agent, talous_agent,
    viestinta_agent, lomake_agent, vapaaehtoiset_agent, laki_agent, kumppanit_agent,
    qa_policy_agent
]

for a in ALL_AGENTS:
    if a:
        a.before_tool_callback = enforce_tool_matrix
        a.after_tool_callback = log_tool_trace

from app.middleware import chain_callbacks, pii_sanitize_middleware

# Chain the middleware: 1. Scrub PII (Ingress/Draft), 2. Check Numeric Integrity
if qa_policy_agent:
    qa_policy_agent.before_model_callback = chain_callbacks(
        pii_sanitize_middleware, 
        qa_numeric_enforcement_callback
    )

    # Egress Scrub on Final Response
    qa_policy_agent.after_model_callback = egress_scrub_callback

samha_pipeline = SequentialAgent(
    name="samha_pipeline",
    sub_agents=[koordinaattori_agent],
    description="Samha Multi-Agent Pipeline with Internal QA Delegation."
)


app = App(root_agent=samha_pipeline, name="app")

# Alias for eval and CLI (must point to the entry point)
root_agent = samha_pipeline
