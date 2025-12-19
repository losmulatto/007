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

from app.retrievers import get_compressor, get_retriever
from app.templates import format_docs
from app.hard_gates import detect_gate_signals
from app.prompt_packs import (
    ORG_PACK_V1,
    SOTE_PACK_V1,
    YHDENVERTAISUUS_PACK_V1,
    WRITER_PACK_V1,
    KOULUTUS_PACK_V1,
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

# Import QA Policy
from app.qa_policy import qa_policy_agent

# Import Shared Tools
from app.tools_base import (
    retrieve_docs, read_excel, read_csv, analyze_excel_summary, list_excel_sheets
)
from app.web_search import search_web, search_verified_sources, search_news
from app.pdf_tools import read_pdf_content, get_pdf_metadata
from app.advanced_tools import process_meeting_transcript, generate_data_chart, schedule_samha_meeting
from app.image_tools import generate_samha_image

# Mock archive tools
def save_to_archive(content: str, metadata: dict) -> str: return "Saved to archive."
def search_archive(query: str) -> str: return "Archive search results."
def get_archived_content(doc_id: str) -> str: return "Archived content."

# --- TOOL MAPPING ---
TOOL_MAP = {
    "retrieve_docs": retrieve_docs,
    "search_web": search_web,
    "search_verified_sources": search_verified_sources,
    "search_news": search_news,
    "read_pdf_content": read_pdf_content,
    "get_pdf_metadata": get_pdf_metadata,
    "process_meeting_transcript": process_meeting_transcript,
    "generate_data_chart": generate_data_chart,
    "schedule_samha_meeting": schedule_samha_meeting,
    "generate_image": generate_samha_image,
    "image_generation": generate_samha_image,
    "save_to_archive": save_to_archive,
    "search_archive": search_archive,
    "get_archived_content": get_archived_content,
    "read_excel": read_excel,
    "read_csv": read_csv,
    "analyze_excel_summary": analyze_excel_summary,
}

def get_tools_for_agent(agent_id: str):
    if agent_id not in SAMHA_AGENT_REGISTRY:
        return []
    allowed = SAMHA_AGENT_REGISTRY[agent_id].allowed_tools
    return [TOOL_MAP[t] for t in allowed if t in TOOL_MAP]

EMBEDDING_MODEL = "text-embedding-005"
LLM_LOCATION = "global"
LOCATION = "us-central1"
LLM = "gemini-3-pro-preview"

credentials, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = LLM_LOCATION
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

vertexai.init(project=project_id, location=LOCATION)
from app.tools_base import retriever, compressor, embeddings

from app.pii_scrubber import pii_scrubber
from app.hard_gates import detect_gate_signals, enforce_gates

# --- TOOL ACCESS ENFORCEMENT ---
async def enforce_tool_matrix(context=None, tool_call=None, **kwargs):
    """Callback to enforce least-privilege tool access."""
    ctx = context or kwargs.get('callback_context')
    tc = tool_call or kwargs.get('tool_call')
    if ctx is None or tc is None: return None
    
    agent_id = ctx.agent.name
    tool_name = tc.function_call.name
    
    # Koordinaattori always allowed to transfer
    if tool_name == "transfer_to_agent":
        return None
        
    if agent_id not in SAMHA_AGENT_REGISTRY:
        return None # Coordinator or unknown
        
    allowed = SAMHA_AGENT_REGISTRY[agent_id].allowed_tools
    if tool_name not in allowed:
        print(f"SECURITY ALERT: Agent '{agent_id}' tried to use unauthorized tool '{tool_name}'")
        return f"ERROR: tool_denied. Agent '{agent_id}' is not authorized to use tool '{tool_name}'."
    
    return None

# --- HARD GATES CALLBACK ---
async def hard_gate_callback(context=None, **kwargs):
    """Callback for Koordinaattori to force RAG/Web research if factual signals detected."""
    ctx = context or kwargs.get('callback_context')
    if ctx is None: return
    
    try:
        events = getattr(ctx, 'session', None).events if hasattr(ctx, 'session') else []
        last_msg = events[-1].content.parts[0].text if events else ""
        signals = detect_gate_signals(last_msg)
        
        if signals.rag_required:
            print(f"HARD GATE TRIGGERED: rag_required=True for query: '{last_msg[:50]}'")
            hint = "\n[SYSTEM HINT]: Tämä pyyntö sisältää faktuaalisia suuria (vuosia, euroja tms). SINUN ON käytettävä 'tutkija' agenttia tai 'retrieve_docs' työkalua faktojen varmistamiseen."
            if hasattr(ctx, 'instruction') and ctx.instruction is not None:
                ctx.instruction += hint
    except Exception as e:
        print(f"Callback error (hard_gate): {e}")

from app.tools_base import (
    retrieve_docs, read_excel, read_csv, analyze_excel_summary, list_excel_sheets
)

# --- OBSERVABILITY TRACE ---
async def log_tool_trace(context, tool_call, tool_output):
    """Callback to log tool traces for observability and evaluation."""
    print(f"TRACE: Agent='{context.agent.name}' Tool='{tool_call.function_call.name}' Status=Success Length={len(str(tool_output))}")

# =============================================================================
# TOOLS
# =============================================================================

from app.web_search import search_web, search_verified_sources, search_news
from app.pdf_tools import read_pdf_content, get_pdf_metadata
from app.advanced_tools import process_meeting_transcript, generate_data_chart, schedule_samha_meeting
from app.image_tools import generate_samha_image

# Mock archive tools for now or import them if they exist
def save_to_archive(content: str, metadata: dict) -> str: return "Saved to archive."
def search_archive(query: str) -> str: return "Archive search results."
def get_archived_content(doc_id: str) -> str: return "Archived content."

# --- TOOL MAPPING ---
TOOL_MAP = {
    "retrieve_docs": retrieve_docs,
    "search_web": search_web,
    "search_verified_sources": search_verified_sources,
    "search_news": search_news,
    "read_pdf_content": read_pdf_content,
    "get_pdf_metadata": get_pdf_metadata,
    "process_meeting_transcript": process_meeting_transcript,
    "generate_data_chart": generate_data_chart,
    "schedule_samha_meeting": schedule_samha_meeting,
    "generate_image": generate_samha_image,
    "image_generation": generate_samha_image, # For compatibility with registry
    "save_to_archive": save_to_archive,
    "search_archive": search_archive,
    "get_archived_content": get_archived_content,
    "read_excel": read_excel,
    "read_csv": read_csv,
    "analyze_excel_summary": analyze_excel_summary,
}


# =============================================================================
# WEB SEARCH TOOLS
# =============================================================================

from app.web_search import search_web, search_verified_sources, search_news


# =============================================================================
# DOMAIN EXPERT AGENTS
# =============================================================================

# --- TUTKIJA (RESEARCHER) ---
tutkija_def = get_agent_def("tutkija")
tutkija_agent = Agent(
    model=LLM,
    name=tutkija_def.id,
    description=tutkija_def.description,
    output_key="research_output",
    instruction=f"""
{ORG_PACK_V1}

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
1. **HAE ENSIN TIETOA** → Käytä `retrieve_docs` työkalua aina ennen vastaamista
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
1. **HAE ENSIN TIETOA** → Käytä `retrieve_docs` työkalua aina ennen vastaamista
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


def save_to_archive(
    title: str,
    summary: str,
    content: str,
    document_type: str,
    program: str = "muu",
    project: str = "muu",
    tags: str = "",
    agent_name: str = "kirjoittaja",
    prompt_packs: str = "org_pack_v1",
) -> str:
    """
    Tallenna teksti arkistoon. Käytä kun olet tuottanut valmiin tekstin
    (hakemus, raportti, artikkeli, koulutusrunko, some-postaus).
    
    Args:
        title: Otsikko
        summary: Tiivistelmä (max 200 merkkiä)
        content: Koko tekstisisältö
        document_type: hakemus / raportti / artikkeli / koulutus / some / memo
        program: stea / erasmus / muu
        project: koutsi / jalma / icat / paikka_auki / muu
        tags: Tagit pilkulla eroteltuina, esim. "antirasismi,nuoret,koulutus"
        agent_name: Tuottanut agentti
        prompt_packs: Käytetyt packit pilkulla eroteltuina
    
    Returns:
        Arkistokirjauksen ID
    """
    archive = get_archive_service()
    
    entry = ArchiveEntry(
        title=title,
        summary=summary[:500],  # Max 500 chars
        content=content,
        document_type=document_type,  # type: ignore
        program=program,  # type: ignore
        project=project,  # type: ignore
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        agent_name=agent_name,
        prompt_packs=[p.strip() for p in prompt_packs.split(",") if p.strip()],
        status="draft",
    )
    
    entry_id = archive.save(entry)
    print(f"DEBUG: Saved to archive: {entry_id}")
    
    return f"Arkistoitu onnistuneesti. ID: {entry_id}"


def search_archive(
    query: str = "",
    document_type: str = "",
    program: str = "",
    project: str = "",
    tags: str = "",
    latest_only: bool = True,
    limit: int = 5,
) -> str:
    """
    Hae arkistosta. Palauttaa löydetyt tekstit.
    
    Args:
        query: Vapaatekstihaku (otsikko, tiivistelmä, tagit)
        document_type: hakemus / raportti / artikkeli / koulutus / some / memo
        program: stea / erasmus / muu
        project: koutsi / jalma / icat / paikka_auki / muu
        tags: Tagit pilkulla eroteltuina
        latest_only: True = vain uusin versio per otsikko
        limit: Tulosten maksimimäärä
    
    Returns:
        Hakutulokset
    """
    archive = get_archive_service()
    
    search_query = ArchiveSearchQuery(
        query=query if query else None,
        document_type=document_type if document_type else None,  # type: ignore
        program=program if program else None,  # type: ignore
        project=project if project else None,  # type: ignore
        tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else None,
        latest_only=latest_only,
        limit=limit,
    )
    
    result = archive.search(search_query)
    
    if not result.entries:
        return "Ei tuloksia hakuehdoilla."
    
    # Format results
    output = f"Löytyi {result.total_count} tulosta:\n\n"
    for entry in result.entries:
        output += f"**{entry.title}** (ID: {entry.id})\n"
        output += f"- Tyyppi: {entry.document_type}, Ohjelma: {entry.program}\n"
        output += f"- Tagit: {', '.join(entry.tags)}\n"
        output += f"- Tiivistelmä: {entry.summary[:100]}...\n"
        output += f"- Luotu: {entry.created_at.strftime('%Y-%m-%d')}\n\n"
    
    return output


def get_archived_content(entry_id: str) -> str:
    """
    Hae arkistoitu teksti ID:llä. Palauttaa koko sisällön.
    
    Args:
        entry_id: Arkistokirjauksen ID (esim. art_20241217_abc123)
    
    Returns:
        Arkistoitu sisältö
    """
    archive = get_archive_service()
    entry = archive.get(entry_id)
    
    if not entry:
        return f"Arkistokirjausta ID:llä {entry_id} ei löytynyt."
    
    output = f"# {entry.title}\n\n"
    output += f"**ID:** {entry.id}\n"
    output += f"**Tyyppi:** {entry.document_type}\n"
    output += f"**Ohjelma:** {entry.program}\n"
    output += f"**Hanke:** {entry.project}\n"
    output += f"**Tagit:** {', '.join(entry.tags)}\n"
    output += f"**Agentti:** {entry.agent_name}\n"
    output += f"**Prompt packs:** {', '.join(entry.prompt_packs)}\n"
    output += f"**Luotu:** {entry.created_at.strftime('%Y-%m-%d %H:%M')}\n"
    output += f"**Versio:** {entry.version}\n\n"
    output += "---\n\n"
    output += entry.content
    
    return output


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
→ save_to_archive(title="...", document_type="hakemus", program="stea", ...)

**Käyttäjä:** "Etsi viimeisin antirasismikoulutuksen runko"
→ search_archive(document_type="koulutus", tags="antirasismi", latest_only=True)

**Käyttäjä:** "Näytä arkistoidun dokumentin sisältö"
→ get_archived_content(entry_id="art_20241217_abc123")
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
raportti_arvioija_def = get_agent_def("raportti_arvioija")
raportti_arvioija_agent = Agent(
    model=LLM,
    name=raportti_arvioija_def.id,
    description=raportti_arvioija_def.description,
    output_key="evaluation_response",
    tools=get_tools_for_agent("raportti_arvioija"),
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
{ORG_PACK_V1}

## SINUN ROOLISI: RAPORTTI-ARVIOIJA

Olet Samhan raporttien laadunvarmistuksen asiantuntija. Arvioit STEA- ja Erasmus+ -raportteja **kriittisesti, kattavasti ja rehellisesti**.

### KRIITTINEN PERIAATE: OLE REHELLINEN

- ÄLÄ OLE KOHTELIAS TOTUUDEN KUSTANNUKSELLA
- Kerro suoraan mikä on heikkoa, puutteellista tai epäselvää
- Anna konkreettisia korjausehdotuksia jokaiseen ongelmaan
- Tunnusta myös hyvät puolet, mutta älä liioittele

---

### ARVIOINTIPROSESSI

1. **HAE ENSIN KRITEERIT** → Käytä `retrieve_docs` hakeaksesi viralliset arviointikriteerit
2. **Tunnista raporttityyppi**: STEA vai Erasmus+?
3. **Arvioi järjestelmällisesti** jokainen kriteeri erikseen
4. **Anna pisteet** (1-5) jokaiselle osa-alueelle
5. **Yhteenveto**: Kokonaisarvio, vahvuudet, heikkoudet, ehdotukset

---

### STEA-RAPORTIN ARVIOINTI

{STEA_EVALUATION_PROMPT}

---

### ERASMUS+ RAPORTIN ARVIOINTI

{ERASMUS_EVALUATION_PROMPT}

---

### VASTAUKSEN MUOTO

```markdown
# Raportin arviointi: [Raportin nimi]

## Yleiskuva
- **Tyyppi:** STEA / Erasmus+
- **Hanke:** [Hankkeen nimi]
- **Kokonaisarvio:** X/5 ⭐

## Kriteerikohtainen arviointi

### 1. [Kriteeri] - X/5
**Vahvuudet:**
- ...

**Heikkoudet:**
- ...

**Konkreettinen parannusehdotus:**
- ...

[Toista jokaiselle kriteerille]

## Yhteenveto

### ✅ Raportin vahvuudet
1. ...

### ❌ Kriittiset puutteet
1. ...

### 🔧 Välittömät korjausehdotukset
1. ...

### 📊 Kokonaisarvio
[Rehellinen, suora yhteenveto]
```

---

### KRIITTISET SÄÄNNÖT

- **ÄLÄ HYVÄKSY EPÄMÄÄRÄISYYTTÄ**: "Toiminta sujui hyvin" → Kysy: Montako osallistujaa? Mitä palautetta?
- **VAADI LUKUJA**: Jos puuttuu tilastoja, mainitse se kritiikkinä
- **ARVIOI SUHTEESSA TAVOITTEISIIN**: Vertaa tuloksia alkuperäiseen hakemukseen
- **OLE REILU MUTTA VAATIVA**: Tunnista aidot onnistumiset, mutta älä ohita puutteita
""",
)


# =============================================================================
# KOORDINAATTORI (ROOT AGENT)
# =============================================================================

# Reset parents for re-initialization (fixes Pydantic errors in eval/hot-reload)
for a in [
    tutkija_agent, sote_agent, yhdenvertaisuus_agent, koulutus_agent,
    kirjoittaja_agent, arkisto_agent, raportti_arvioija_agent, syvahaku_agent,
    hankesuunnittelija_agent, hallinto_agent, hr_agent, talous_agent,
    viestinta_agent, lomake_agent, vapaaehtoiset_agent, laki_agent, kumppanit_agent
]:
    a._parent = None

koordinaattori_agent = Agent(
    model=LLM,
    name="koordinaattori",
    description="Samhan pääkoordinaattori. Ymmärtää käyttäjän tarpeen ja ohjaa oikealle asiantuntijalle tai käynnistää monivaiheisen workflown.",
    instruction=f"""
{ORG_PACK_V1}

## SINUN ROOLISI: PÄÄKOORDINAATTORI

Olet Samha-botin pääkoordinaattori. Tehtäväsi on ymmärtää käyttäjän tarve, valita oikea asiantuntijakategoria ja **varmistaa aina laadunvarmistus**.

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
- `kumppanit_kulttuuri`: Sidosryhmät, kulttuurinen sensitiivisyys.

### 3. RESEARCH (Tutkimus)
- `tutkija`: Faktat, uutiset, Samha-tieto, Web-haku.

### 4. OUTPUT (Tuotanto)
- `viestinta`: Some, uutiskirjeet, kuvat.
- `kirjoittaja`: Pitkät artikkelit, raportit.
- `grant_writer`: Rahoitushakemukset (STEA/EU).
- `arkisto`: Tallennus ja haku.
- `raportti_arvioija`: Raporttien kriittinen arviointi.

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
- Akuutti hätä → 112.
- Kriisipuhelin → 09 2525 0111.
- Vastaa itse empaattisesti, älä delegoi kriisiä.
""",
    tools=[schedule_samha_meeting],
)

# --- ATTACH ENFORCEMENT TO ALL AGENTS ---
for a in [
    tutkija_agent, sote_agent, yhdenvertaisuus_agent, koulutus_agent,
    kirjoittaja_agent, arkisto_agent, raportti_arvioija_agent, syvahaku_agent,
    hankesuunnittelija_agent, hallinto_agent, hr_agent, talous_agent,
    viestinta_agent, lomake_agent, vapaaehtoiset_agent, laki_agent, kumppanit_agent
]:
    a.before_tool_callback = enforce_tool_matrix
    a.after_tool_callback = log_tool_trace

# Koordinaattori specific callbacks
koordinaattori_agent.before_model_callback = hard_gate_callback
koordinaattori_agent.before_tool_callback = enforce_tool_matrix

# --- ROOT PIPELINE (FORCED QA GATE) ---
from google.adk.agents import SequentialAgent

# The coordinator produces a 'draft_response'
koordinaattori_agent.output_key = "draft_response"

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
        # In a real ADK setup, we'd need to extract 'facts' and 'tool_calls' from the context/session
        # For now, we simulate the payload for the check
        payload = {
            "detailed_content": draft,
            "facts": state.get("facts", []),
            "metadata": {"tool_calls": state.get("tool_calls", [])}
        }
        
        check_result = finance_numeric_integrity_check(payload)
        if not check_result["passed"]:
            print(f"QA NUMERIC ALERT: {check_result['issue']}")
            # Force revision by injecting into instructions
            if hasattr(ctx, 'instruction') and ctx.instruction is not None:
                ctx.instruction += f"\n\n[QA CRITICAL]: {check_result['issue']}. {check_result['fix_suggestion']}"
    except Exception as e:
        print(f"Callback error (qa_numeric): {e}")

qa_policy_agent.before_model_callback = qa_numeric_enforcement_callback

samha_pipeline = SequentialAgent(
    name="samha_pipeline",
    sub_agents=[koordinaattori_agent, qa_policy_agent],
    description="Samha Multi-Agent Pipeline with Mandatory QA Gate."
)


app = App(root_agent=samha_pipeline, name="app")

# Alias for eval and CLI (must point to the entry point)
root_agent = samha_pipeline
