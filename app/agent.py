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
from app.contracts_loader import load_contract

from app.env import load_env

load_env()

import google
import vertexai
from google.adk.agents import Agent, SequentialAgent
from google.adk.apps.app import App
from google.genai import types as genai_types
from langchain_google_vertexai import VertexAIEmbeddings

# =============================================================================
# Gemini 3 Configuration - No Temperature!
# =============================================================================
# Per Gemini 3 best practices: keep temperature at default (1.0)
# Control quality via thinking_level instead

from app.gemini3_config import (
    LONG_OUTPUT_CONFIG,
    CRITIC_CONFIG,
    MODEL_FLASH,
    MODEL_PRO,
    USE_PRO,
    pick_model,
    gen_config,
    PROFILE_WRITER,
    PROFILE_CRITIC,
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
from app.hankesuunnittelija import grant_writer_agent, get_proposal_reviewer
from app.ammattilaiset import hallinto_agent, hr_agent, talous_agent, get_specialist_agent
from app.viestinta import viestinta_agent
from app.lomakkeet import lomake_agent
from app.vapaaehtoiset import vapaaehtoiset_agent
from app.laki import laki_agent
from app.kumppanit import kumppanit_agent

# Global Specialists (Directly accessible to Koordinaattori)
methods_expert = get_specialist_agent("koulutus", suffix="_global")
writer_expert = get_specialist_agent("kirjoittaja", suffix="_global")
# ... other specialists could be added here ...

from app.agents_registry import SAMHA_AGENT_REGISTRY, get_agent_def, LEADERSHIP, DOMAIN_EXPERT, RESEARCH, OUTPUT, QA_POLICY
from app.tool_ids import ToolId
from google.adk import agents as adk_agents
from typing import Any, Dict

# Import QA Policy
from app.qa_policy import qa_policy_agent


from app.tools_registry import TOOL_MAP
from app.model_router import attach_model_router

def get_tools_for_agent(agent_id: str):
    if agent_id not in SAMHA_AGENT_REGISTRY:
        return []
    allowed = SAMHA_AGENT_REGISTRY[agent_id].allowed_tools
    return [TOOL_MAP[t] for t in allowed if t in TOOL_MAP]

EMBEDDING_MODEL = "text-embedding-005"
LLM_LOCATION = "global"
LOCATION = "us-central1"
LLM = "gemini-3-flash-preview"
LLM_PRO = "gemini-3-flash-preview"



credentials, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = LLM_LOCATION
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "True")

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
                "web_required": bool(getattr(signals, 'web_required', False)), # Added web_required
                "signals": active_signals,
                "raw": last_msg[:400]
            }
            if signals.rag_required or signals.web_required:
                print(f"HARD GATE STATE SET: rag={session.state['hard_gate']['rag_required']} web={session.state['hard_gate']['web_required']}")
            
            # Inject State into Instruction (Phase 1.9 Fix)
            if hasattr(ctx, 'instruction'):
                state_str = str(session.state["hard_gate"])
                ctx.instruction += f"\n\n[SYSTEM STATE]: {state_str}"

    except Exception as e:
        print(f"Callback error (hard_gate): {e}")

# --- PROGRAMMATIC DELEGATION CALLBACK ---
# Map of agent IDs that can be targeted directly
# Includes both backend names and frontend aliases
TARGETABLE_AGENTS = {
    # Core agents
    "tutkija", "sote", "yhdenvertaisuus", "koulutus", "kirjoittaja",
    "arkisto", "syvahaku", "grant_writer", "hallinto", "hr", "talous",
    "viestinta", "lomakkeet", "vapaaehtoiset", "laki_gdpr", "kumppanit",
    "qa_policy", "qa_quality", "methods_expert", "writer_expert",
    # Frontend ID aliases
    "proposal_reviewer", 
    "lomakkeet_expert",
    "raportti_arvioija",
    # Special agents
    "kriitikko",
}

async def forced_delegation_callback(callback_context=None, llm_request=None, **kwargs):
    """
    Programmatic delegation callback.
    
    If session.state['target_agent'] is set and matches a known sub-agent,
    this callback returns an LlmResponse that forces a transfer_to_agent call,
    bypassing the LLM entirely for the first turn.
    
    This is only triggered once per session (tracked via '_delegation_done' flag).
    """
    ctx = callback_context or kwargs.get('callback_context') or kwargs.get('context')
    if ctx is None:
        return None
    
    try:
        session = getattr(ctx, 'session', None)
        if not session or not hasattr(session, 'state'):
            return None
        
        state = session.state
        
        # Check if we already delegated in this session
        if state.get('_delegation_done'):
            return None
        
        target = state.get('target_agent')
        if not target or target.lower() == 'koordinaattori':
            return None
        
        # Normalize target name
        target_normalized = target.lower().replace('-', '_').replace(' ', '_')
        
        if target_normalized not in TARGETABLE_AGENTS:
            print(f"[Forced Delegation] Target '{target}' not in allowed list, skipping")
            return None
        
        # Map frontend aliases to actual backend agent names
        ALIAS_MAP = {
            "proposal_reviewer": "proposal_reviewer",
            "raportti_arvioija": "proposal_reviewer",
            "lomakkeet_expert": "lomakkeet",
            "lomakkeet": "lomakkeet",
            "laki_gdpr": "laki",
            "some": "viestinta",
            "kriitikko": "qa_quality",
            "qa_critic": "qa_quality",
        }
        actual_agent = ALIAS_MAP.get(target_normalized, target_normalized)
        
        # Mark as delegated to avoid looping
        state['_delegation_done'] = True
        
        print(f"[Forced Delegation] Programmatically transferring to: {actual_agent}")
        
        # Return an LlmResponse that forces transfer_to_agent
        from google.genai import types
        from google.adk.models.llm_response import LlmResponse
        
        # Create a function call to transfer_to_agent
        transfer_call = types.FunctionCall(
            name="transfer_to_agent",
            args={"agent_name": actual_agent}
        )
        
        # Build the response with the function call
        response_content = types.Content(
            role="model",
            parts=[types.Part(function_call=transfer_call)]
        )
        
        return LlmResponse(content=response_content)
        
    except Exception as e:
        print(f"[Forced Delegation] Error: {e}")
        import traceback
        traceback.print_exc()
        return None

from app.tools_base import (
    retrieve_docs, read_excel, read_csv, analyze_excel_summary, list_excel_sheets
)

# --- OBSERVABILITY TRACE ---
# Imported from app.observability
# observability trace imported above
from app.egress import scrub_for_user, ensure_sources_payload
from app.web_search import search_web, search_verified_sources, search_news, search_legal_sources
from app.pdf_tools import read_pdf_content, get_pdf_metadata
from app.advanced_tools import process_meeting_transcript, generate_data_chart, schedule_samha_meeting
from app.image_tools import generate_samha_image

# =============================================================================
# DOMAIN EXPERT AGENTS
# =============================================================================

# --- TUTKIJA (RESEARCHER) with Deep Search v2 ---
from app.deep_search import get_research_pipeline
from google.adk.tools.agent_tool import AgentTool

tutkija_def = get_agent_def("tutkija")
tutkija_agent = Agent(
    model=LLM_PRO,
    name=tutkija_def.id,
    description="Samhan tutkija-agentti (v2). Käyttää RAG:ia ja Deep Searchia verifioidun tiedon hakuun.",
    output_key="draft_response",
    instruction=f"""
<role>
Olet Samhan tutkija-agentti (v2). Tehtäväsi on hakea tarkkaa, lähteistettyä tietoa ja toimia faktantarkistajana.
</role>

<context>
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}
{load_contract("tutkija")}
</context>

<instructions>
1. **VAIHE 0: Input-analyysi**: Tunnista tutkimustaso (pika/syvä/auditointi) ja kielitarve.
2. **VAIHE 1: Tiedonhaku**:
   - Sisäinen tieto -> `retrieve_docs`
   - Ulkoinen/laaja tieto -> Delegoi `research_pipeline`-agentille (Deep Search)
3. **VAIHE 2: Tulosten analyysi**:
   - Luo **Väite + Lähde** -parit. Älä jätä väitettä ilman verifioitua lähdettä.
4. **VAIHE 3: Itsecheck**: Lisää loppuun v2-sopimuksen mukainen 3-rivinen laatucheck.
</instructions>

<constraints>
- ÄLÄ hallusinoi lähteitä.
- Merkitse tiedon hakuajankohta.
- Deep Search on ensisijainen ulkoiseen hakuun.
</constraints>

<output_format>
### Tutkimustulos

**Pääväite:** [Yhteenveto]

**Löydökset:**
- [Väite] -> [Lähde/Linkki]
- ...

---

**Output-laadun itsecheck:**
- Lähteet: [ok/puuttuu]
- Hallusinaatioriski: [matala/huomattava]
- Tuoreus: [pvm]
</output_format>
""",
    tools=[retrieve_docs, read_pdf_content],
    sub_agents=[get_research_pipeline()],
)



# --- SOTE-ASIANTUNTIJA v2 ---
sote_def = get_agent_def("sote")
sote_agent = Agent(
    model=LLM,
    name=sote_def.id,
    description=sote_def.description,
    output_key="draft_response",
    tools=get_tools_for_agent("sote"),
    instruction=f"""
<role>
Olet Samhan sote-asiantuntija (v2). Vastaat huoliin ja kysymyksiin empaattisesti, turvallisesti ja diagnosoimatta.
</role>

<context>
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}
{SOTE_PACK_V1}
{load_contract("sote")}
</context>

<instructions>
1. **VAIHE 0: Input-analyysi**: Tunnista `case_type` ja onko kyseessä kriisi (`urgent`).
2. **VAIHE 1: Kuuntelu ja Validointi**: Aloita aina empaattisesti.
3. **VAIHE 2: Tiedonhaku**: Käytä `retrieve_docs` löytääksesi Samha-palveluohjausta.
4. **VAIHE 3: Ohjaus**: Anna 2-3 konkreettista askelta tai palvelua.
5. **VAIHE 4: Itsecheck**: Lisää loppuun v2-sopimuksen mukainen 4-rivinen laatucheck.
</instructions>

<constraints>
- **EI DIAGNOSOINTIA**. Älä nimeä sairauksia.
- **KRIISI = OHJAA HETI**: 112 tai kriisipuhelin 09 2525 0111.
- Pysy Samha-tonessa: empaattinen rinnallakulkija.
</constraints>

<output_format>
### Vastaus

[Empaattinen ja normalisoiva kuuleminen]

**Ehdotukseni:**
- [Konkreettinen askel 1]
- ...

**Palvelut ja tuki:**
- [Palvelu + linkki/yhteystieto]

---

**Output-laadun itsecheck:**
- Empatiataso: [ok/parannettavaa]
- Turvallisuus: [ok/vaatii ohjausta]
- Ei-diagnosointi: ok
- Jatkoaskel: [annettu askel]
</output_format>
""",
)



# --- YHDENVERTAISUUS-ASIANTUNTIJA v2 ---
yhdenvertaisuus_def = get_agent_def("yhdenvertaisuus")
yhdenvertaisuus_agent = Agent(
    model=LLM,
    name=yhdenvertaisuus_def.id,
    description=yhdenvertaisuus_def.description,
    output_key="yhdenvertaisuus_response",
    tools=get_tools_for_agent("yhdenvertaisuus"),
    instruction=f"""
<role>
Olet Samhan antirasismi- ja yhdenvertaisuustyön asiantuntija (v2). Autat tunnistamaan rakenteita ja puuttumaan syrjintään.
</role>

<context>
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}
{YHDENVERTAISUUS_PACK_V1}
{load_contract("yhdenvertaisuus")}
</context>

<instructions>
1. **VAIHE 0: Input-analyysi**: Tunnista `case_type` (syrjintä/koulutus/yleinen) ja kohderyhmä.
2. **VAIHE 1: Kuuntelu ja Validointi**: Usko ja validoi kokemus välittömästi.
3. **VAIHE 2: Rakenteiden nimeäminen**: Nimeä ilmiö (esim. rakenteellinen rasismi, mikroaggressio).
4. **VAIHE 3: Toiminta-ohjeet**: Anna 2-3 konkreettista askelta voimaannuttamiseen TAI puuttumiseen.
5. **VAIHE 4: Itsecheck**: Lisää loppuun 3-rivinen laatucheck (kielen sensitiivisyys, rakenteellisuus, jatkoaskel).
</instructions>

<constraints>
- KÄYTÄ "IHMISET ENSIN" -KIELTÄ.
- ÄLÄ KOSKAAN kyseenalaista syrjintäkokemusta.
- Tunnista rasismiin liittyvä trauma.
</constraints>

<output_format>
### Vastaus

[Validoiva ja empaattinen aloitus]

**Rakenteellinen analyysi:**
- [Ilmiön kuvaus ja nimeäminen]

**Ehdotukset ja jatko:**
- [Konkreettinen teko 1]
- ...

---

**Output-laadun itsecheck:**
- Sensitiivinen kieli: ok
- Rakenteellisuus: ok
- Jatkoaskel: [annettu askel]
</output_format>
""",
)



# --- KOULUTUSSUUNNITTELIJA PIPELINE ---
koulutus_def = get_agent_def("koulutus")

koulutus_draft_agent = Agent(
    model=LLM,
    name="koulutus_draft",
    description="Drafts education plans based on Training Contract v2.",
    output_key="koulutus_draft",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=get_tools_for_agent("koulutus"),
    instruction=f"""
<role>
Olet Samhan koulutussuunnittelija (v2). Luot osallistavia ja pedagogisesti laadukkaita koulutuskokonaisuuksia.
</role>

<context>
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}
{KOULUTUS_PACK_V1}
{load_contract("koulutus")}
</context>

<instructions>
1. **VAIHE 0: Input-analyysi**: Tunnista formaatti, kohderyhmä ja oppimistavoite.
2. **VAIHE 1: Tiedonhaku**: Käytä `retrieve_docs` Samhan aiemmista menetelmistä.
3. **VAIHE 2: Suunnittelu**: Luo dynaaminen runko format:in mukaan (Työpaja/Webinaari).
4. **VAIHE 3: Itsecheck**: Lisää loppuun v2-sopimuksen mukainen 4-rivinen laatucheck.
</instructions>

<constraints>
- Noudata 20 min sääntöä: maksimi kesto luennoinnille.
- Korosta osallisuutta ja turvallisempaa tilaa.
- Aikataulu minuuttitasolla.
</constraints>

<output_format>
# [Koulutuksen nimi]

[Sisältö v2-rakenteen mukaan: tavoitteet, aikataulu, harjoitteet]

---

**Output-laadun itsecheck:**
- Interaktiivisuus-ratio: [X% akt / Y% pass]
- Turvallisempi tila: [ok/puuttuu]
- Selkokielisyys: [ok/huomio]
- Suurin riski: [lause]
</output_format>
""",
)

koulutus_refiner_agent = Agent(
    model=LLM,
    name="koulutus_refiner",
    description="Refines education plans.",
    output_key="koulutus_response",
    instruction="""
<role>
Olet laadunvarmistaja koulutussuunnitelmille.
</role>

<instructions>
1. Lue edellinen koulutussuunnitelma (koulutus_draft)
2. Tarkista ja korjaa:
   - Poista tyhjät fraasit -> muuta konkreettisiksi harjoitteiksi
   - Varmista aikataulun täsmällisyys
   - Varmista "seuraavat askeleet" -osio
3. Palauta korjattu suunnitelma
</instructions>

<constraints>
- Säilytä rakenne
- ÄLÄ lyhennä sisältöä
- Muuta vain epämääräiset kohat konkreettisiksi
</constraints>
""",
)

koulutus_agent = SequentialAgent(
    name=koulutus_def.id,
    description=koulutus_def.description,
    sub_agents=[koulutus_draft_agent, koulutus_refiner_agent]
)



# --- KIRJOITTAJA PIPELINE ---
kirjoittaja_def = get_agent_def("kirjoittaja")

kirjoittaja_draft_agent = Agent(
    model=LLM,
    name="kirjoittaja_draft",
    description="Drafts various content types based on Samha Writer Contract v2.",
    output_key="kirjoittaja_draft",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=get_tools_for_agent("kirjoittaja"),
    instruction=f"""
<role>
Olet Samhan ammattikirjoittaja (v2). Tuotat dynaamista ja vaikuttavaa sisältöä eri kanaviin.
</role>

<context>
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}
{WRITER_PACK_V1}
{load_contract("kirjoittaja")}
</context>

<instructions>
1. **VAIHE 0: Input-analyysi**:
   - Tunnista tai oleta: `document_type`, `audience`, `goal`, `length`.
   - Jos inputteja puuttuu, tee selkeä oletus ja ilmoita se tekstin alussa.

2. **VAIHE 1: Tiedonhaku ja Perustelu**:
   - Käytä `retrieve_docs` Samha-tiedon hakuun.
   - Luokittele väitteet v2-sopimuksen mukaan: (1) lähteistetty fakta, (2) toiminnallinen kuvaus, (3) kokemushavainto.

3. **VAIHE 2: Kirjoittaminen**:
   - Valitse rakenne `document_type`:n mukaan (Artikkeli/Some/Raportti).
   - Käytä dynaamista rakennetta, älä pakota mekaanisia sääntöjä.

4. **VAIHE 3: Itsecheck**:
   - Lisää AINA loppuun v2-sopimuksen mukainen 4-rivinen laatucheck.
</instructions>

<constraints>
- Vältä passiivin ylikäyttöä, mutta käytä sitä luonnollisesti tarvittaessa.
- Vaihtele subjektia ("samha", "tiimi", "ohjaajat").
- ÄLÄ hallusinoi lähteitä; jos et voi varmistaa faktaa, muotoile se toiminnalliseksi kuvaukseksi tai kokemushavainnoksi.
- Konkretia AINA: mitä, kuka, kuinka usein.
</constraints>

<output_format>
[Oletus: document_type, audience, goal - jos puuttuivat]

# [Otsikko / Koukkuavaus]

[Sisältö dynaamisesti document_type:n mukaan]

---

**Output-laadun itsecheck:**
- Konkretia: [ok/puuttuu]
- Lähteet: [ok/puuttuu]
- CTA: [ok/puuttuu]
- Riskit: [yksi lause]
</output_format>
""",
)

kirjoittaja_refiner_agent = Agent(
    model=LLM,
    name="kirjoittaja_refiner",
    description="Refines content based on Writer Contract v2.",
    output_key="final_article",
    instruction=f"""
<role>
Olet Samha-sisällön päätoimittaja. Hiot tekstin julkaisukuntoon v2-sopimuksen mukaisesti.
</role>

<context>
{load_contract("kirjoittaja")}
</context>

<instructions>
1. **Lue luonnos** (`kirjoittaja_draft`).
2. **Tarkista v2-standardit**:
   - Onko rakenne dynaaminen ja kanavaan sopiva?
   - Ovatko lähteet luokiteltu oikein (fakta/toiminta/kokemus)?
   - Onko passiivi/aktiivi tasapainossa ja subjekti vaihteleva?
   - Onko anonymisointi kunnossa?
3. **Korjaa ja viilaa**:
   - Poista fraasit ja lisää konkretiaa.
   - Varmista "ihmiset ensin" -sävy.
4. **Viimeistele itsecheck**.
</instructions>

<constraints>
- ÄLÄ muuta dynaamista rakennetta mekaaniseksi.
- Varmista että "Next Steps" ovat mukana jos goal sitä vaatii.
</constraints>

<output_format>
[Lopullinen hiottu sisältö]

---

**Output-laadun itsecheck:**
- Konkretia: ok
- Lähteet: ok
- CTA: ok
- Riskit: [viimeistelty analyysi]
</output_format>
""",
)

kirjoittaja_agent = SequentialAgent(
    name=kirjoittaja_def.id,
    description=kirjoittaja_def.description,
    sub_agents=[kirjoittaja_draft_agent, kirjoittaja_refiner_agent]
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
<role>
Olet Samhan arkistoagentti. Tehtäväsi on tallentaa valmiita tekstejä arkistoon ja hakea aiempia tuotoksia.
</role>

<context>
{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}
{load_contract("arkisto")}
</context>

<instructions>
1. **Tunnista pyyntö**: Onko kyseessä tallennus vai haku?
2. **Tallennus**: Käytä `save_to_archive` oikeilla metatiedoilla
3. **Haku**: Käytä `search_archive` ja palauta tulokset
4. **Sisältö**: Käytä `get_archived_content` täyteen sisältöön
</instructions>

<constraints>
- AINA valitse oikea document_type: hakemus, raportti, artikkeli, koulutus, some, memo
- AINA valitse ohjelma: stea, erasmus, muu
- AINA valitse hanke: koutsi, jalma, icat, paikka_auki, muu
- AINA lisää relevantit tagit
</constraints>

<examples>
### Esimerkki 1: Tallennus
Käyttäjän viesti: "Tallenna tämä Stea-hakemus"
Oikea toiminta: Kutsu save_to_archive(title="...", document_type="hakemus", program="stea", ...)

### Esimerkki 2: Haku
Käyttäjän viesti: "Etsi viimeisin antirasismikoulutuksen runko"
Oikea toiminta: Kutsu search_archive(document_type="koulutus", tags="antirasismi", latest_only=True)

### Esimerkki 3: Sisältö
Käyttäjän viesti: "Näytä arkistoidun dokumentin sisältö"
Oikea toiminta: Kutsu get_archived_content(entry_id="art_20241217_abc123")
</examples>

<output_format>
### Arkistotoiminto

**Toiminto:** [Tallennus/Haku/Sisältö]
**Tulos:** [Onnistumisviesti tai hakutulokset]
</output_format>
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
<role>
Olet "THE ENFORCER" - radikaali laadunvarmistaja, jonka tehtävänä on suojella julkisia varoja epämääräisiltä tai sektorin ulkopuolisilta hankkeilta.
</role>

<context>
{RADICAL_AUDITOR_PACK_V1}
{QA_PORT_PACK_V1}
{GOLD_FAILURE_PACK_V1}
{FUNDING_TYPES_PACK_V1}
</context>

<instructions>
1. **DESTRUCTION PHASE (Red Team)**: Listaa ENSIN 3 kriittistä syytä, miksi tämä hanke on tällä hetkellä epäonnistuminen
2. **Pisteytys**: Käytä 0-100 asteikkoa (61 = alin läpäisypiste)
3. **Sektoripoliisi**: Tarkista rahoitusinstrumentin mukaisuus
4. **ROADMAP**: Anna konkreettiset korjausehdotukset pistetavoitteeseen 81+
</instructions>

<constraints>
- AINA aloita kritiikillä (Destruction Phase)
- ÄLÄ anna läpäisyä ilman perusteluja
- 61 = alin hyväksyttävä pistemäärä
- Konkreettiset, toimenpiteelliset korjausehdotukset
</constraints>

<examples>
### Esimerkki: Heikko hakemus
Käyttäjän viesti: "Arvioi tämä STEA-hakemus: [liian yleinen kuvaus]"
Oikea toiminta:
1. Listaa 3 puutetta: epämääräiset tavoitteet, puuttuvat mittarit, epäselvä kohderyhmä
2. Anna pisteet: 45/100
3. Ehdota: "Lisää SMART-tavoitteet, määrittele 3 mitattavaa tulosta, kuvaa kohderyhmä tarkemmin"
</examples>

<output_format>
# Hakemusarviointi: RADICAL AUDIT REPORT

## Destructive Analysis (Red Team)
- [Kriittinen puute 1]
- [Kriittinen puute 2]
- [Kriittinen puute 3]

## Kokonaispisteet: XX / 100

## Vahvuudet
- [Vahvuus 1]
- [Vahvuus 2]

## ROADMAP TO 81+ (Actionable Remediation)
- [Konkreettinen korjaus 1]
- [Konkreettinen korjaus 2]
- [Konkreettinen korjaus 3]
</output_format>
""",
)



# =============================================================================
# KOORDINAATTORI (ROOT AGENT)
# =============================================================================

# Reset parents for re-initialization (fixes Pydantic errors in eval/hot-reload)
for a in [
    tutkija_agent, sote_agent, yhdenvertaisuus_agent, koulutus_agent,
    kirjoittaja_agent, arkisto_agent, syvahaku_agent,
    grant_writer_agent, hallinto_agent, hr_agent, talous_agent,
    viestinta_agent, lomake_agent, vapaaehtoiset_agent, laki_agent, kumppanit_agent,
    methods_expert, writer_expert
]:
    a._parent = None

from app.qa_quality import qa_quality_agent

koordinaattori_agent = Agent(
    model=LLM_PRO,
    name="koordinaattori",
    description="Samhan pääkoordinaattori. Ymmärtää käyttäjän tarpeen ja ohjaa oikealle asiantuntijalle tai käynnistää monivaiheisen workflown.",
    output_key="draft_response",
    instruction=f"""
## DOKUMENTTIEN ANALYYSI (DIRECT)
Jos käyttäjän viestissä on tekstiä (SISÄLTÖ: ...), analysoi se ensisijaisena lähteenä.
Voit myös käyttää `read_pdf_content` -työkalua jos haluat tarkistaa koko dokumentin uudestaan.

{ORG_PACK_V1}
{CRITICAL_REFLECTION_PACK_V1}

## SINUN ROOLISI: PÄÄKOORDINAATTORI

Olet Samha-botin pääkoordinaattori. Tehtäväsi on ymmärtää käyttäjän tarve, valita oikea asiantuntijakategoria ja **varmistaa aina laadunvarmistus**.
## TÄRKEÄÄ: CHAT VS TUOTANTO
- Jos käyttäjä kysyy kyvyistäsi tai tervehtii, vastaa empaattisesti ja suoraan ilman QA-portteja.
- Jos käyttäjä kysyy "Osaatko arvioida...", vahvista kykysi ja ohjeista häntä lataamaan dokumentti.


---

### [TÄRKEÄÄ: AGENTIN KOHDENNUS]
Tarkista session tilasta `target_agent`:
- Jos `target_agent` on asetettu (esim. "tutkija", "sote", "koulutus"), **DELEGOI VÄLITTÖMÄSTI** kyseiselle agentille ilman omaa tervehdystäsi.
- Käyttäjä haluaa puhua nimenomaan kyseiselle asiantuntijalle.
- Huom: Jos `target_agent` on "koordinaattori" tai puuttuu, toimi normaalisti pääkoordinaattorina.

---

### TIEDOKSI: TILAKONE (HARD GATES)
# State injected below: [SYSTEM STATE]: {{...}}

Tarkista yllä olevasta tilasta `rag_required`:
- Jos `rag_required` == True -> **SINUN ON pakko delegoida ensin `tutkija`-agentille**.
- ÄLÄ KOSKAAN vastata itse luvuilla tai faktoilla jos `rag_required` on päällä.
- Huom: Jos `target_agent` on jo `tutkija`, tämä on jo hoidettu.
Tarkista myös `web_required`:
- Jos `web_required` == True -> **DELEGOI `tutkija`-agentille ja vaadi `search_verified_sources`**.

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
- `qa_quality`: Tuotosten laadunvarmistus.

---



---

## HARD GATES (TIEDOSTOT & FAKTAT)

Jos pyyntö sisältää:
- **TIEDOSTOJA (PDF)**: Jos viestissä on `[ATTACHMENT: ...]` ja polku (Path: ...), **SINUN ON PAKKO** delegoida asiantuntijalle ja käskeä häntä lukemaan tiedosto työkalulla `read_pdf_content`.
- **FAKTAT (Vuodet, €, %, nimet)**: **PAKOTA AINA** haku: delegoi ensin `tutkija` agentille keräämään faktat Samhan tietokannasta.
- **LASKUT**: Delegoi `talous` ja vaadi `python_interpreter`-työkalua.

---

## MITEN TOIMIT

1. **Analysoi**: Tunnista käyttäjän tarve.
2. **Delegoi**: Ohjaa tehtävä oikealle asiantuntijalle.
3. **Vastaa**: Kerro käyttäjälle mitä olet tekemässä ja kuka asiantuntija hoitaa tehtävän.


<delegation_rules>
## KRIITTINEN: DELEGOINTI TYÖKALULLA

Kun haluat siirtää tehtävän asiantuntijalle, KUTSU `transfer_to_agent` -TYÖKALUA.

ÄLÄ kirjoita delegointia tekstinä. SE EI TOIMI.
KÄYTÄ AINA työkalukutsua.

### Käytettävissä olevat asiantuntijat:
| Nimi | Tehtävä |
|------|---------|
| grant_writer | Rahoitushakemukset (STEA, Erasmus+) |
| tutkija | Faktojen haku, tiedonhaku |
| proposal_reviewer_specialist | Hakemusten arviointi |
| kirjoittaja | Pitkät artikkelit, raportit |
| sote | Mielenterveys, hyvinvointi |
| talous | Budjetit, kirjanpito |

</delegation_rules>

<examples>
### ESIMERKKI 1: Käyttäjä pyytää analysoimaan hakemusta
Käyttäjän viesti: "Analysoi tämä Erasmus-hakemus"
Oikea toiminta: Kutsu transfer_to_agent työkalu parametrilla agent_name="grant_writer"

### ESIMERKKI 2: Käyttäjä kysyy faktoista
Käyttäjän viesti: "Kuinka monta nuorta Suomessa kärsii mielenterveysongelmista?"
Oikea toiminta: Kutsu transfer_to_agent työkalu parametrilla agent_name="tutkija"

### ESIMERKKI 3: Käyttäjä pyytää arvioimaan raporttia
Käyttäjän viesti: "Arvioi tämä loppuraportti"
Oikea toiminta: Kutsu transfer_to_agent työkalu parametrilla agent_name="proposal_reviewer_specialist"
</examples>

<constraints>
- ÄLÄ KOSKAAN kirjoita "Siirretään grant_writerille" tekstinä
- KÄYTÄ AINA transfer_to_agent -työkalua
- Jos epäröit, delegoi `tutkija`-agentille ensin
</constraints>


---

## KRIISITILANTEET (EHDOTON)
- Akuutti hätä -> 112.
- Kriisipuhelin -> 09 2525 0111.
- Vastaa itse empaattisesti, älä delegoi kriisiä.
""",
    tools=get_tools_for_agent("koordinaattori"),
    sub_agents=[
        tutkija_agent, sote_agent, yhdenvertaisuus_agent, koulutus_agent,
        kirjoittaja_agent, arkisto_agent, syvahaku_agent,
        grant_writer_agent, hallinto_agent, hr_agent, talous_agent,
        viestinta_agent, lomake_agent, vapaaehtoiset_agent, laki_agent, kumppanit_agent,
        qa_policy_agent, qa_quality_agent, get_proposal_reviewer(suffix="_specialist"),
        # Global Specialists for Manual/Direct use
        methods_expert, writer_expert
    ]
)

# Koordinaattori specific callbacks - chain forced delegation + hard gates
if koordinaattori_agent:
    # forced_delegation_callback runs first and may return LlmResponse to bypass LLM
    # hard_gate_callback runs second if delegation didn't happen
    koordinaattori_agent.before_model_callback = [forced_delegation_callback, hard_gate_callback]

# --- ROOT PIPELINE (FORCED QA GATE) ---
from google.adk.agents import SequentialAgent

# The coordinator produces a 'draft_response'
# koordinaattori_agent.output_key = "draft_response" # Set in constructor

# The QA agent specifically reviews 'draft_response'
qa_policy_agent.instruction += "\n\nTARKISTA TÄMÄ TEKSTI (draft_response): {draft_response?}"

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

async def parse_qa_decision_callback(context=None, **kwargs):
    """Callback to extract DECISION: [APPROVE/REJECT] from QA output."""
    ctx = context or kwargs.get('callback_context')
    if ctx is None: return
    
    try:
        session = getattr(ctx, 'session', None)
        state = session.state if session and hasattr(session, 'state') else {}
        output = state.get("final_response", "")
        
        if "DECISION: APPROVE" in output:
            state["qa_decision"] = "APPROVE"
        elif "DECISION: NEEDS_REVISION" in output:
            state["qa_decision"] = "NEEDS_REVISION"
        elif "DECISION: REJECT" in output:
            state["qa_decision"] = "REJECT"
            
    except Exception as e:
        print(f"Callback error (parse_qa): {e}")

async def egress_scrub_callback(context=None, **kwargs):
    """Ensure final output is scrubbed."""
    ctx = context or kwargs.get('callback_context')
    try:
        session = getattr(ctx, "session", None)
        if session and hasattr(session, "state"):
            final = session.state.get("final_response", "")
            if final:
                _hydrate_sources_from_events(session)
                scrubbed = scrub_for_user(final)
                session.state["final_response"] = scrubbed
                ensure_sources_payload(session.state, scrubbed)
    except Exception as e:
        print(f"Egress Scrub Error: {e}")


def _hydrate_sources_from_events(session):
    """Populate sources from tool responses if missing."""
    state = session.state if session and hasattr(session, "state") else {}
    sources = state.get("sources")
    if isinstance(sources, dict) and sources:
        return
    sources = {} if not isinstance(sources, dict) else sources
    url_to_short_id = state.get("url_to_short_id")
    if not isinstance(url_to_short_id, dict):
        url_to_short_id = {}
    id_counter = len(url_to_short_id) + 1

    for event in getattr(session, "events", []) or []:
        responses = []
        if hasattr(event, "get_function_responses"):
            responses = event.get_function_responses() or []
        for response in responses:
            name = getattr(response, "name", None)
            if name not in ("search_web", "search_news", "search_verified_sources", "google_search"):
                continue
            text = getattr(response, "response", None)
            if isinstance(text, dict):
                for key in ("result", "content", "output", "text"):
                    nested = text.get(key)
                    if nested:
                        text = nested
                        break
            if not text:
                continue
            for item in _extract_sources_from_search_output(str(text)):
                url = item.get("url")
                if not url:
                    continue
                if url not in url_to_short_id:
                    short_id = f"src-{id_counter}"
                    url_to_short_id[url] = short_id
                    sources[short_id] = {
                        "short_id": short_id,
                        "title": item.get("title") or _domain_from_url(url),
                        "url": url,
                        "domain": _domain_from_url(url),
                        "supported_claims": [],
                    }
                    id_counter += 1

    if sources:
        state["sources"] = sources
        state["url_to_short_id"] = url_to_short_id


# --- CALLBACK ATTACHMENT ---
qa_policy_agent.after_model_callback = parse_qa_decision_callback

from app.viestinta import viestinta_agent, viestinta_draft_agent, viestinta_refiner_agent
from app.hankesuunnittelija import (
    idea_generator, 
    writer_section_intro, writer_section_methods, proposal_finalizer,
    proposal_reviewer, samha_context_checker, trend_planner
)

ALL_AGENTS = [
    koordinaattori_agent, tutkija_agent, sote_agent, yhdenvertaisuus_agent, 
    koulutus_draft_agent, koulutus_refiner_agent,
    kirjoittaja_draft_agent, kirjoittaja_refiner_agent, 
    viestinta_draft_agent, viestinta_refiner_agent,
    arkisto_agent, syvahaku_agent,
    grant_writer_agent, hallinto_agent, hr_agent, talous_agent,
    viestinta_agent, lomake_agent, vapaaehtoiset_agent, laki_agent, kumppanit_agent,
    qa_policy_agent, qa_quality_agent,
    idea_generator, 
    writer_section_intro, writer_section_methods, proposal_finalizer,
    proposal_reviewer, samha_context_checker, trend_planner,
    methods_expert, writer_expert
]

for a in ALL_AGENTS:
    if a:
        if hasattr(a, "before_tool_callback"):
            a.before_tool_callback = enforce_tool_matrix
        if hasattr(a, "after_tool_callback"):
            a.after_tool_callback = log_tool_trace

async def ensure_draft_response_middleware(context=None, **kwargs):
    """Ensures draft_response exists in state before QA."""
    ctx = context or kwargs.get('callback_context')
    if ctx and hasattr(ctx, 'session'):
        state = ctx.session.state
        if "draft_response" not in state or not state["draft_response"]:
             # Comprehensive list of potential response keys from all specialists
             response_keys = [
                 "talous_response", "research_output", "sote_response", 
                 "hallinto_response", "hr_response", "viestinta_response",
                 "koulutus_response", "laki_response", "lomake_response",
                 "vapaaehtoiset_response", "kumppanit_response", "final_article",
                 "proposal_draft"
             ]
             for key in response_keys:
                 if key in state and state[key]:
                     state["draft_response"] = state[key]
                     break
             else:
                 state["draft_response"] = "Ei aiempaa vastausluonnosta analysoitavaksi."

from app.middleware import chain_callbacks, pii_sanitize_middleware

# Chain the middleware: 1. Ensure context, 2. Scrub PII (Ingress/Draft), 3. Check Numeric Integrity
if qa_policy_agent:
    qa_policy_agent.before_model_callback = chain_callbacks(
        ensure_draft_response_middleware,
        pii_sanitize_middleware, 
        qa_numeric_enforcement_callback
    )

    # Chain the Egress Scrub and Parser for QA Decision
    qa_policy_agent.after_model_callback = chain_callbacks(
        parse_qa_decision_callback,
        egress_scrub_callback
    )

for a in ALL_AGENTS:
    attach_model_router(a)

samha_pipeline = SequentialAgent(
    name="samha_pipeline",
    sub_agents=[koordinaattori_agent],
    description="Samha Multi-Agent Pipeline with Internal QA Delegation."
)


app = App(root_agent=koordinaattori_agent, name="app")

# Alias for eval and CLI (must point to the entry point)
root_agent = koordinaattori_agent

# Attach model router fixes (Gemini 3 signatures, routing, response fixer)
from app.model_router import attach_to_all_agents
attach_to_all_agents(root_agent)
