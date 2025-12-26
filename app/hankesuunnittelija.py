# Copyright 2025 Samha
"""
Hankesuunnittelija - Project Planning Workflow

Orchestrates a full project planning workflow through all specialist agents:
1. syvahaku: Deep research on topic & trends
2. sote_asiantuntija: Health & wellbeing perspective
3. yhdenvertaisuus_asiantuntija: Equality & anti-racism perspective
4. koulutussuunnittelija: Training & methods
5. kirjoittaja: Final grant application

Flow:
    User: "Ideoi hanke nuorten mielenterveyden edistämiseksi"
           V
    [1] trend_researcher -> tutkii trendit ja rahoittajaprioriteetit
           V
    [2] idea_generator -> ideoi 3-5 hankekonseptia
           V
    [3] sote_validator -> arvioi sote-näkökulmasta
           V
    [4] yhdenvertaisuus_validator -> arvioi yhdenvertaisuusnäkökulmasta
           V
    [5] methods_planner -> suunnittelee menetelmät
           V
    [6] proposal_writer -> kirjoittaa hakemuksen
           V
    [7] proposal_reviewer -> arvioi ja antaa palautetta
           V
    Final: Valmis hankesuunnitelma
"""

import datetime
import logging
import re
from typing import AsyncGenerator
from google.genai import types as genai_types
from google.adk.agents import LlmAgent, SequentialAgent, LoopAgent, BaseAgent
from google.adk.events import Event, EventActions
from google.adk.agents.invocation_context import InvocationContext
from app.contracts_loader import load_contract
from app.prompt_packs import (
    ORG_PACK_V1,
    QA_PORT_PACK_V1,
    GOLD_FAILURE_PACK_V1,
    RADICAL_AUDITOR_PACK_V1,
    RADICAL_AUDITOR_PACK_V2,  # Maximum criticality multi-funder evaluation
    CRITICAL_REFLECTION_PACK_V1,
    FUNDING_TYPES_PACK_V1,
    WRITER_PACK_V1,
    SOTE_PACK_V1,
    YHDENVERTAISUUS_PACK_V1,
)
from app.tool_ids import ToolId
from app.tools_registry import TOOL_MAP

# Define reusable tool sets
RESEARCH_TOOLS = [
    TOOL_MAP[ToolId.RETRIEVE_DOCS],
    TOOL_MAP[ToolId.SEARCH_WEB],
    TOOL_MAP[ToolId.SEARCH_VERIFIED],
    TOOL_MAP[ToolId.SEARCH_NEWS],
    TOOL_MAP[ToolId.READ_PDF]
]
BASIC_TOOLS = [TOOL_MAP[ToolId.RETRIEVE_DOCS]]

# Import Deep Search Pipeline
from app.deep_search import get_research_pipeline, syvahaku_agent, get_syvahaku_agent
from app.ammattilaiset import arkisto_agent


# =============================================================================
# LOOP CONTROL & CUSTOM AGENTS
# =============================================================================


class RevisionChecker(BaseAgent):
    """
    Tarkistaa arvioinnin pisteet ja päättää jatketaanko iterointia.
    
    - Lopettaa loopin jos pisteet >= 85 (hyvä hakemus)
    - Lopettaa loopin jos 3 kierrosta tehty
    - Muuten jatkaa korjauskierrokselle
    
    IMPORTANT: Uses state flag 'stop_revision_loop' to signal stop,
    because 'escalate' may not work as expected in all ADK versions.
    """
    
    # Pydantic-yhteensopivat kentät
    min_score: int = 85
    max_iterations: int = 3
    
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        # Hae laatuarviointi session statesta
        # Uusi arkkitehtuuri tallentaa tuloksen avaimeen 'field_qa_result'
        qa_result = ctx.session.state.get("field_qa_result", "")
        
        # Päätöslogiikka: Etsi avainsanoja tekstistä
        is_pass = False
        score = 0
        
        if isinstance(qa_result, str):
            # Etsi "PÄÄTÖS: [PASS / NEEDS_REVISION]" -muotoa
            if "PÄÄTÖS: PASS" in qa_result or "PÄÄTÖS: [PASS]" in qa_result:
                is_pass = True
            
            # Fallback: Etsi silti pisteitä jos niitä on (esim. "Score: 90/100")
            match = re.search(r'Score:\s*(\d+)', qa_result)
            if match:
                score = int(match.group(1))
            elif is_pass:
                score = 100 # Jos pass mutta ei pisteitä, simuloidaan täydet
        elif isinstance(qa_result, dict):
            decision = qa_result.get("decision", "").upper()
            is_pass = (decision == "PASS")
            score = qa_result.get("score", 100 if is_pass else 0)
        
        # Hae iteraatiolaskuri
        iteration = ctx.session.state.get("revision_count", 0)
        
        logging.info(f"[{self.name}] Result: {'PASS' if is_pass else 'REVISE'}, Score: {score}/100, Iteration: {iteration}/{self.max_iterations}")
        print(f"[{self.name}] Result: {'PASS' if is_pass else 'REVISE'}, Score: {score}/100, Iteration: {iteration}/{self.max_iterations}")
        
        # Päätöslogiikka - aseta stop flag stateen
        should_stop = False
        
        if is_pass or score >= self.min_score:
            logging.info(f"[{self.name}] Hakemus hyväksytty. Lopetetaan iterointi.")
            print(f"[{self.name}] ✅ PASS")
            should_stop = True
            ctx.session.state["revision_result"] = "PASS"
        elif iteration >= self.max_iterations:
            logging.info(f"[{self.name}] Max iteraatiot saavutettu ({iteration} >= {self.max_iterations}). Lopetetaan.")
            print(f"[{self.name}] ⏹️ MAX ITERATIONS - Stopping at iteration {iteration}")
            should_stop = True
            ctx.session.state["revision_result"] = "MAX_ITERATIONS"
        else:
            # Jatka korjauskierrokselle
            ctx.session.state["revision_count"] = iteration + 1
            logging.info(f"[{self.name}] Jatketaan korjauskierrokselle {iteration + 1}")
            print(f"[{self.name}] 🔄 CONTINUE - Starting revision {iteration + 1}")
            ctx.session.state["revision_result"] = "CONTINUE"
        
        # Set the stop flag for LoopAgent
        ctx.session.state["stop_revision_loop"] = should_stop
        
        # Use escalate=True to break out of LoopAgent
        if should_stop:
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            yield Event(author=self.name)


# =============================================================================
# CONFIGURATION - Using Gemini 3 Best Practices
# =============================================================================

# Import centralized Gemini 3 config
from app.gemini3_config import (
    pick_model,
    gen_config,
    PROFILE_PLANNER,
    PROFILE_RESEARCH,
    PROFILE_WRITER,
    PROFILE_CRITIC,
    PROFILE_VALIDATOR,
    LONG_OUTPUT_CONFIG,
    CRITIC_CONFIG,
    MODEL_FLASH,
    MODEL_PRO,
    USE_PRO,
)

# Model selection (respects USE_PRO flag)
WORKER_MODEL = MODEL_FLASH
PLANNER_MODEL = MODEL_FLASH
PRO_MODEL = MODEL_PRO if USE_PRO else MODEL_FLASH

# NOTE: Temperature removed! Gemini 3 guide recommends keeping default (1.0)
# Quality is now controlled via thinking_level in the model itself


# =============================================================================
# WORKFLOW AGENTS
# =============================================================================

# Step 1: Trend Research
# Step 1: Deep Search Integration (Trend Analysis)

# Phase 0: Samha Context Check
samha_context_checker = LlmAgent(
    model=WORKER_MODEL,
    name="samha_context_checker",
    description="Ensures research alignment with Samha values and target groups.",
    instruction=f"""
<role>
Olet Samhan kontekstitarkistaja. Varmistat, että hankeideat ovat linjassa Samhan arvojen ja kohderyhmien kanssa.
</role>

<context>
{load_contract("tutkija")}
{ORG_PACK_V1}
</context>

<instructions>
1. Tarkista Samhan kohderyhmät: maahanmuuttajat, syrjäytymisriskissä olevat nuoret
2. Tarkista arvot: kulttuurisensitiivisyys, matalan kynnyksen palvelut
3. Jos idea on ristiriidassa, ilmoita SELKEÄSTI
4. Jos OK, kirjaa konteksti seuraavaa vaihetta varten
</instructions>

<constraints>
- ÄLÄ hyväksy ideoita jotka ovat selvästi Samhan arvojen vastaisia
- AINA käytä retrieve_docs tarkistaaksesi organisaation tiedot
</constraints>

<output_format>
### Kontekstitarkistus

**Tila:** [HYVÄKSYTTY / HYLÄTTY]
**Kohderyhmä:** [Keitä hanke palvelee]
**Arvot:** [Mitkä Samhan arvot toteutuvat]
**Huomiot:** [Mahdolliset varoitukset]
</output_format>
""",
    tools=[TOOL_MAP[ToolId.RETRIEVE_DOCS]],
    output_key="samha_context",
)

# Phase 1: Auto-Planning (Automated Trend Planner)
trend_planner = LlmAgent(
    model=PLANNER_MODEL,
    name="trend_planner",
    description="Generates an automated research plan for trend analysis.",
    instruction=f"""
<role>
Olet tutkimussuunnittelija. Luot automaattisen suunnitelman trendianalyysiin.
</role>

<instructions>
1. Lue konteksti Phase 0:sta: {{samha_context}}
2. Luo 5-kohtainen tutkimussuunnitelma:
   - Nykyiset trendit ja tilastot
   - Sopivat rahoitusinstrumentit (STEA, EU, Säätiöt)
   - Kohderyhmän tarpeet (Samhan ryhmät)
   - Benchmarkit ja innovaatiot
</instructions>

<constraints>
- OUTPUT LANGUAGE: FINNISH
- ÄLÄ pyydä käyttäjän hyväksyntää - tämä on automatisoitu pipeline
- Jokainen rivi alkaa `[RESEARCH]`-tagilla
</constraints>

<output_format>
- [RESEARCH] [Tutkimuskohde 1]
- [RESEARCH] [Tutkimuskohde 2]
- [RESEARCH] [Tutkimuskohde 3]
- [RESEARCH] [Tutkimuskohde 4]
- [RESEARCH] [Tutkimuskohde 5]
</output_format>
""",
    output_key="research_plan",
)




# Step 2: Idea Generation
idea_generator = LlmAgent(
    model=PLANNER_MODEL,
    name="idea_generator",
    description="Ideoi ja valitsee parhaan hankekonseptin trendianalyysin pohjalta.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
<role>
Olet Samhan hankeideoija. Luot ja valitset innovatiivisia hankekonsepteja tutkimustiedon pohjalta.
</role>

<context>
{load_contract("hankesuunnittelija")}
{ORG_PACK_V1}
{FUNDING_TYPES_PACK_V1}
</context>

<instructions>
1. Lue trendianalyysi: {{final_cited_report}}
2. Ideoi 3 innovatiivista hankekonseptia, jotka vastaavat löydettyihin tarpeisiin.
3. Valitse 1 suositeltu konsepti, joka parhaiten sopii Samhan strategiaan.
4. Tee alustava instrumenttisuositus (STEA, Erasmus+, Säätiöt...).
</instructions>

<constraints>
- ÄLÄ vielä lukitse lopullisesti kaikkia sääntöjä, `project_planner` ja `template_analyzer` hienosäätävät ne.
- Keskity strategiseen valintaan ja innovaatioon.
</constraints>

<output_format>
## Suositeltu konsepti: [Nimi]
**Rahoitustaho:** [Esim. STEA]
**Miksi:** [Perustelu]
**Ydinidea:** [Lyhyt kuvaus]

---
## Muut vaihtoehdot
...
</output_format>
""",
    tools=BASIC_TOOLS,
    output_key="project_ideas",
)


# --- PHASE 2: PROJECT PLANNING (The Planning Engine) ---

project_planner = LlmAgent(
    model=PRO_MODEL,
    name="project_planner",
    description="Tuottaa yksityiskohtaisen hankesuunnitelman (v2) valitun idean pohjalta.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
<role>
Olet Samhan johtava hankesuunnittelija (v2). Tehtäväsi on muuttaa hankeidea konkreettiseksi, mitattavaksi ja realistiseksi suunnitelmaksi.
</role>

<context>
{load_contract("hankesuunnittelija")}
{ORG_PACK_V1}
{FUNDING_TYPES_PACK_V1}
</context>

<instructions>
1. Lue valittu hankeidea: {{project_ideas}} tai {{user_feedback}}.
2. Tuota 5 ydinartefaktia sopimus v2:n mukaisesti:
   - **Project Brief**: Ongelma -> Ratkaisu -> Samha-fit.
   - **Tulosketju / Logframe**: Panokset -> Toiminnot -> Tulokset (määrälliset ja laadulliset mittarit).
   - **Implementation Map**: Työpaketit, aikataulu (kvartaalit) ja vastuut.
   - **Budget Logic**: Kululajit ja niiden välttämättömyys toiminnoille.
   - **Risk & Safeguarding**: 8-12 riskiä, mitigointi ja omistajat.

3. Tee **Instrument Lock**: Päätä ja lukitse `selected_instrument` ja `non_negotiables`.
</instructions>

<constraints>
- Noudata AINA {load_contract("hankesuunnittelija")} laatuankkureita (Realism, Funder-fit, Measurability, Compliance).
- ÄLÄ hallusinoi; käytä {{final_cited_report}} tilastoja ja lähteitä.
- Varmista että budjetti ja työmäärä ovat realistisia.
</constraints>

<output_format>
```json
{{
  "selected_instrument": "stea_ak / erasmus_ka152 / ...",
  "non_negotiables": ["Rule 1", "Rule 2", ...],
  "project_brief": {{ "problem": "...", "solution": "...", "samha_fit": "..." }},
  "logframe": [ {{ "level": "outcome", "statement": "...", "kpis": ["..."] }} ],
  "implementation_map": [ {{ "period": "Q1", "tasks": ["..."] }} ],
  "budget_logic": [ {{ "category": "Personnel", "justification": "..." }} ],
  "risks": [ {{ "risk": "...", "mitigation": "..." }} ]
}}
```
</output_format>
""",
    output_key="project_plan"
)




# Step 3: SOTE Validation
sote_validator = LlmAgent(
    model=WORKER_MODEL,
    name="sote_validator",
    description="Arvioi hankeidean sote-näkökulmasta.",
    instruction=f"""
<role>
Olet SOTE-asiantuntija hankeideoiden validointiin. Arvioit hankkeiden mielenterveys- ja hyvinvointinäkökulmat.
</role>

<context>
{load_contract("sote")}
{CRITICAL_REFLECTION_PACK_V1}
</context>

<instructions>
1. Lue hankeideat: {{project_ideas}}
2. Lue mahdollinen aiempi palaute: {{proposal_review?}}
3. Arvioi SUOSITELTU hankeidea seuraavista näkökulmista:
   - Mielenterveyden tuki
   - Kynnykset ja saavutettavuus
   - Kokonaisvaltainen hyvinvointi
   - Turvallisuus
   - Rajapinnat lääketieteelliseen hoitoon
</instructions>

<constraints>
- VAROITA jos löydät "hoito/terapia"-termejä
- ÄLÄ hyväksy hankkeita jotka kuuluvat terveydenhuoltoon
- TUNNISTA onko kyseessä nuorisotyö vai sote-palvelu
</constraints>

<output_format>
### SOTE-arviointi

**Sektorin tarkistus:** [Nuorisotyö / Sote-rajapinta / Sote-palvelu]

**Mielenterveys & Hyvinvointi:**
- [Arvio]

**Kynnykset & Saavutettavuus:**
- [Arvio]

**Turvallisuus:**
- [Arvio]

**Varoitusmerkit:**
- [Lista tai "Ei varoitusmerkkejä"]

**Sote-status:** [Puhas nuorisotyö / Sote-rajapinta / Sote-hanke]
</output_format>
""",
    tools=BASIC_TOOLS,
    output_key="sote_validation",
)


# Step 4: Equality Validation
yhdenvertaisuus_validator = LlmAgent(
    model=WORKER_MODEL,
    name="yhdenvertaisuus_validator",
    description="Arvioi hankeidean yhdenvertaisuusnäkökulmasta.",
    instruction=f"""
<role>
Olet yhdenvertaisuusasiantuntija hankeideoiden validointiin. Arvioit hankkeiden inklusiivisuuden ja antirasismitoimet.
</role>

<context>
{load_contract("yhdenvertaisuus")}
{CRITICAL_REFLECTION_PACK_V1}
</context>

<instructions>
1. Lue hankeideat: {{project_ideas}}
2. Lue SOTE-arviointi: {{sote_validation}}
3. Lue mahdollinen aiempi palaute: {{proposal_review?}}
4. Arvioi SUOSITELTU hankeidea seuraavista näkökulmista:
   - Saavutettavuus
   - Inkluusio
   - Antirasismi
   - Intersektionaalisuus
   - Osallisuus (ovatko nuoret tekijöitä vai kohteita)
</instructions>

<constraints>
- VAADI osallisuutta: nuorten tulee olla tekijöitä, ei vain kohteita
- VAADI intersektionaalisuutta: huomioi risteävät identiteetit
</constraints>

<output_format>
### Yhdenvertaisuusarviointi

**Saavutettavuus:**
- [Arvio]

**Inkluusio & Antirasismi:**
- [Arvio]

**Osallisuusaste:** [1-5], [Perustelu]

**Parannusehdotukset:**
- [Ehdotus 1]
- [Ehdotus 2]

**Yhdenvertaisuus-status:** [Erinomainen / Kehitettävää / Puutteellinen]
</output_format>
""",
    tools=BASIC_TOOLS,
    output_key="yhdenvertaisuus_validation",
)



# Step 5: Methods Planning
methods_planner = LlmAgent(
    model=PLANNER_MODEL,
    name="methods_planner",
    description="Suunnittelee hankkeen menetelmät ja toiminnot.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
<role>
Olet koulutussuunnittelija menetelmien suunnitteluun. Luot konkreettisia, osallistavia toimintasuunnitelmia.
</role>

<context>
{load_contract("koulutus")}
{CRITICAL_REFLECTION_PACK_V1}
</context>

<instructions>
1. Lue syötteet:
   - Hankeideat: {{project_ideas}}
   - SOTE-arviointi: {{sote_validation}}
   - Yhdenvertaisuusarviointi: {{yhdenvertaisuus_validation}}
   - Mahdollinen palaute: {{proposal_review?}}
2. Suunnittele menetelmät rahoitusinstrumentin mukaan:
   - Erasmus+ = non-formaali oppiminen
   - STEA = sosiaalinen tuki/neuvonta
3. Luo konkreettinen toimintasuunnitelma
</instructions>

<constraints>
- ÄLÄ sekoita Erasmus+ ja STEA-menetelmiä
- AINA sisällytä osallistavat menetelmät
- AINA sisällytä mittarit
</constraints>

<output_format>
### Menetelmäsuunnitelma

**Menetelmäyhteenveto:** [Non-formaali oppiminen / Sosiaalinen tuki]

**Vuosi 1 - Toiminnot:**
| Kuukausi | Toiminto | Osallistujat | Mittari |
|----------|----------|--------------|---------|
| 1-3 | [Toiminto] | [N kpl] | [Mittari] |
| ... | ... | ... | ... |

**Materiaalit:**
- [Materiaali 1]
- [Materiaali 2]

**Resurssit:**
- [Resurssi 1]
- [Resurssi 2]
</output_format>
""",
    tools=BASIC_TOOLS,
    output_key="methods_plan",
)



# Step 6: Proposal Writing (Phase A: Needs & Context)
writer_section_intro = LlmAgent(
    model=PLANNER_MODEL,
    name="writer_section_intro",
    description="Kirjoittaa hakemuksen tarveperustelut ja taustatiedot.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
<role>
Olet hakemuksen kirjoittaja (Osa 1: Tarve & Tausta). Kirjoitat perusteellisia tarveanalyysejä.
</role>

<context>
{load_contract("kirjoittaja")}
</context>

<instructions>
1. Lue syötteet:
   - Trendianalyysi: {{final_cited_report}}
   - Hankeideat: {{project_ideas}}
   - Mahdollinen palaute: {{proposal_review?}}

2. Jos on olemassa aiempi arviointi (proposal_review):
   - Lue kritiikki ja korjaa vaaditut kohdat
   - Raportoi muutokset vastauksen alussa

3. Kirjoita hakemuksen alkuosat:
   - Hankkeen nimi ja lyhyt kuvaus
   - Tarve ja tausta (miksi juuri nyt?)
   - Kohderyhmä (ketä auttaa?)
</instructions>

<constraints>
- KIRJOITA YKSITYISKOHTAISESTI - älä tiivistä
- KÄYTÄ trendianalyysin faktoja ja lähteitä
- ÄLÄ jätä tilastoja pois
</constraints>

<output_format>
# [Hankkeen nimi]

## Lyhyt kuvaus
[2-3 lausetta]

## Tarve ja tausta
[Laaja analyysi, 500+ sanaa, lähteet mukana]

## Kohderyhmä
[Keitä, kuinka monta, miksi juuri heitä]
</output_format>
""",
    tools=BASIC_TOOLS,
    output_key="proposal_section_intro",
)

# Step 7: Proposal Writing (Phase B: Implementation & Methods)
writer_section_methods = LlmAgent(
    model=PLANNER_MODEL,
    name="writer_section_methods",
    description="Kirjoittaa hakemuksen toteutus- ja menetelmäosiot.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
<role>
Olet hakemuksen kirjoittaja (Osa 2: Toteutus & Menetelmät). Kirjoitat konkreettisia toimintasuunnitelmia.
</role>

<context>
{load_contract("kirjoittaja")}
</context>

<instructions>
1. Lue syötteet:
   - Menetelmäsuunnitelma: {{methods_plan}}
   - Hankeideat: {{project_ideas}}
   - SOTE & Yhdenvertaisuus: {{sote_validation}}, {{yhdenvertaisuus_validation}}
   - Mahdollinen palaute: {{proposal_review?}}

2. Jos on aiempi arviointi:
   - Lue kritiikki menetelmiin liittyen
   - Korjaa vaaditut kohdat
   - Raportoi muutokset alussa

3. Kirjoita hakemuksen ydin:
   - Tavoitteet (SMART-muodossa)
   - Toiminnot ja menetelmät (jokainen erikseen)
   - Resurssit (kuka tekee, mitä tarvitaan)
</instructions>

<constraints>
- KIRJOITA YKSITYISKOHTAISESTI - älä tiivistä
- Jokainen työpaja ja menetelmä erikseen
- SMART-tavoitteet taulukkona
</constraints>

<output_format>
## Tavoitteet

| Tavoite | Indikaattori | Lähtötaso | Tavoite | Aikataulu |
|---------|--------------|-----------|---------|-----------|
| [Tavoite 1] | [Mittari] | [Nyt] | [Tavoite] | [Milloin] |
...

## Toiminnot ja menetelmät

### Toimenpide 1: [Nimi]
**Mitä:** [Kuvaus]
**Kenelle:** [Kohderyhmä]
**Milloin:** [Aikataulu]
**Vastuuhenkilö:** [Kuka]

### Toimenpide 2: [Nimi]
...

## Resurssit
- [Resurssi 1]
- [Resurssi 2]
</output_format>
""",
    tools=BASIC_TOOLS,
    output_key="proposal_section_methods",
)


# Step 8: Proposal Writing (Phase C: Finalizer)
proposal_finalizer = LlmAgent(
    model=PLANNER_MODEL,
    name="proposal_finalizer",
    description="Yhdistää hakemuksen osat ja lisää vaikuttavuuden.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
<role>
Olet hakemuksen viimeistelijä (Osa 3: Vaikuttavuus & Kooste). Tuotat täydellisen, ammattimaisesti viimeistellyn hakemuksen.
</role>

<context>
{load_contract("kirjoittaja")}
</context>

<instructions>
1. **HAE HAKEMUSPOHJA** (pakollinen):
   - Erasmus+: retrieve_docs("Erasmus KA hakemus pohja struktuuri")
   - STEA: retrieve_docs("STEA hakemus pohja rakenne")

2. Lue aiemmilta agenteilta:
   - Trendianalyysi: {{final_cited_report}}
   - Hankeideat: {{project_ideas}}
   - SOTE-validointi: {{sote_validation}}
   - Yhdenvertaisuus: {{yhdenvertaisuus_validation}}
   - Menetelmäsuunnitelma: {{methods_plan}}

3. Kirjoita TÄYDELLINEN HAKEMUS (kaikki 11 osiota):
</instructions>

<constraints>
- KIRJOITA LAAJASTI - minimi 15 000 merkkiä, tavoite 35 000
- ÄLÄ tiivistä - käytä koko sallittu merkkiraja
- ÄLÄ jätä mitään osiota tyhjäksi

**MERKKIRAJAT PER OSIO:**
| Osio | Min | Max |
|------|-----|-----|
| Tiivistelmä | 800 | 1500 |
| Tarve ja tausta | 2000 | 5000 |
| Tavoitteet | 1500 | 3000 |
| Toimenpiteet | 3000 | 8000 |
| Kohderyhmä | 1000 | 2500 |
| Aikataulu | 1000 | 2000 |
| Seuranta | 1500 | 3000 |
| Vaikuttavuus | 2000 | 4000 |
| Kestävyys | 1000 | 2500 |
| Budjetti | 1000 | 2000 |
| Lähteet | 500 | 1500 |
</constraints>

<output_format>
# [Hankkeen nimi]

## 1. Tiivistelmä
[800-1500 merkkiä]

## 2. Tarve ja tausta
[2000-5000 merkkiä, tilastot ja tutkimus]

## 3. Tavoitteet
[SMART-taulukko]

## 4. Toimenpiteet
[Jokainen toimenpide erikseen, 3000-8000 merkkiä]

## 5. Kohderyhmä
[Taulukko + kuvaukset]

## 6. Aikataulu
[Kuukausi/kvartaali -taso]

## 7. Seuranta
[Mittarit, menetelmät, vastuut]

## 8. Vaikuttavuus
[Lyhyt + pitkä + rakenteellinen]

## 9. Kestävyys
[Jatkuvuussuunnitelma]

## 10. Budjetti
[Pääryhmät + perustelut]

## 11. Lähteet
[Kaikki käytetyt lähteet]
</output_format>
""",
    tools=BASIC_TOOLS,
    output_key="proposal_draft",
)


# =============================================================================
# CRITERIA FETCHER - Separate agent for fetching evaluation criteria
# =============================================================================
# Per Gemini 3 best practices: separate "criteria search" from "evaluation"
# This reduces hallucination and makes evaluation more consistent

criteria_fetcher = LlmAgent(
    model=WORKER_MODEL,
    name="criteria_fetcher",
    description="Hakee arvioinnin kriteerit tietokannasta ennen varsinaista auditointia.",
    generate_content_config=gen_config(PROFILE_RESEARCH, max_output_tokens=4096),
    tools=RESEARCH_TOOLS,
    instruction=f"""
<role>
Olet kriteerihakija. Tehtäväsi on hakea oikeat arviointikriteerit ennen varsinaista auditointia.
</role>

<instructions>
1. **Tunnista dokumenttityyppi**:
   - HAKEMUS: "haemme", "suunnittelemme", "budjettiesitys"
   - LOPPURAPORTTI: "saavutimme", "toteutuneet kulut", "osallistujamäärä oli"

2. **Tunnista rahoittaja**:
   - Erasmus+: "Erasmus+", "EU", "KA1", "KA2"
   - STEA: "STEA", "avustus", "tuloksellisuusraportti"
   - Säätiö: säätiön nimi

3. **Hae kriteerit työkalulla**:
   - STEA hakemus -> retrieve_docs("STEA 2026 hakuohjeet kriteerit")
   - Erasmus+ hakemus -> retrieve_docs("Erasmus+ Programme Guide quality criteria")
   - STEA raportti -> retrieve_docs("STEA tuloksellisuusraportointi kriteerit")
   - Erasmus+ raportti -> retrieve_docs("Erasmus+ final report assessment")
</instructions>

<output_format>
{{
  "document_type": "[HAKEMUS/LOPPURAPORTTI]",
  "funder": "[STEA/ERASMUS+/SÄÄTIÖ]",
  "criteria_source": "[Haun lähde]",
  "criteria": [
    {{"name": "[Kriteerin nimi]", "weight": "[Painoarvo %]", "description": "[Kuvaus]"}},
    ...
  ],
  "threshold": "[Läpäisyraja esim. 85/100]"
}}
</output_format>
""",
    output_key="criteria_brief",
)


# Step 9: Proposal & Report Review (Dynamic Criteria Discovery)

def get_proposal_reviewer(suffix=""): 
    return LlmAgent( 
        model=PLANNER_MODEL, 
        name=f"proposal_reviewer{suffix}", 
        output_key="draft_response", 
        generate_content_config=CRITIC_CONFIG, 
        tools=[],  # No tools needed - criteria already fetched by criteria_fetcher
        description="Arvioi hakemuksia JA loppuraportteja rahoittajakohtaisten kriteerien perusteella.", 
        instruction=f"""
<role>
Olet "THE ENFORCER" - Universal Document Auditor. Suojelet julkisia varoja epämääräisiltä hankkeilta.
</role>

<context>
{ORG_PACK_V1}
{RADICAL_AUDITOR_PACK_V2}
{QA_PORT_PACK_V1}
{GOLD_FAILURE_PACK_V1}
{FUNDING_TYPES_PACK_V1}
{load_contract("proposal_reviewer")}
</context>

<instructions>
## VAIHE 1: LUE KRITEERIT

Lue tilasta (jos saatavilla): `criteria_brief`
- Dokumenttityyppi (HAKEMUS/LOPPURAPORTTI)
- Rahoittaja (STEA/ERASMUS+/SÄÄTIÖ)
- Arviointikriteerit ja painoarvot


## VAIHE 2: DESTRUCTION PHASE (Red Team)

Listaa ENSIN 3 kriittistä puutetta dokumentista.

## VAIHE 3: PISTEYTYS

Pisteytä jokainen kriteeri:
- HAKEMUS: 0-100 pistettä, läpäisy 85+
- STEA-raportti: 1-5 asteikko, läpäisy 4+
- Erasmus-raportti: 0-100 pistettä, läpäisy 75+

## VAIHE 4: KORJAUSOHJEET

Anna TÄSMÄLLISET korjausohjeet jokaiselle puutteelle.
</instructions>

<constraints>
- ÄLÄ hae kriteerejä itse - käytä criteria_brief:iä tilasta
- ALOITA AINA kritiikillä (Destruction Phase)
- Konkreettiset korjausehdotukset
</constraints>

<output_format>
# Arviointi: DYNAMIC AUDIT REPORT

**Dokumenttityyppi:** [HAKEMUS / LOPPURAPORTTI]
**Rahoittaja:** [Tunnistettu]

---

## Destructive Analysis (3 kriittisintä puutetta)
1. [Puute 1]
2. [Puute 2]
3. [Puute 3]

---

## Pisteytys kriteereittäin

| Kriteeri | Pisteet | Kommentti |
|----------|---------|-----------|
| ... | XX/XX | ... |

**Kokonaispisteet: XX / 100**

---

## Päätös
[HYVÄKSY / KORJAA / HYLKÄÄ]

---

## ROADMAP (Korjausohjeet)
1. [Korjaus 1]
2. [Korjaus 2]
3. [Korjaus 3]
</output_format>
""",
    )


async def ensure_proposal_draft_callback(context=None, **kwargs):
    """Ensures proposal_draft exists in state before proposal_reviewer runs."""
    ctx = context or kwargs.get("callback_context")
    if ctx and hasattr(ctx, "session"):
        state = ctx.session.state
        if "proposal_draft" not in state or not state["proposal_draft"]:
            # Try to find content from various sources
            for key in ["draft_response", "user_input", "final_response"]:
                if key in state and state[key]:
                    state["proposal_draft"] = state[key]
                    break
            else:
                state["proposal_draft"] = "Ei asiakirjaa saatavilla. Liitä tarkistettava hakemus tai loppuraportti viestiin."

proposal_reviewer = get_proposal_reviewer()
proposal_reviewer.before_model_callback = ensure_proposal_draft_callback
from app.ammattilaiset import get_arkisto_agent, get_specialist_agent
from google.adk.agents import SequentialAgent

# Fresh instances for the automated pipeline to avoid parentage conflicts
# with the manual coordinator's sub_agents.

# =============================================================================
# NEW FIELD-BASED GRANT WRITER ARCHITECTURE
# =============================================================================
# Core principle: NO TEMPLATE, NO WRITE
# Writer only writes to fields defined in funder_requirements

from app.grant_writer_fields import (
    FieldType, 
    FieldRequirement, 
    FunderRequirements,
    classify_field_type,
    validate_field,
    generate_compliance_report,
    UNIVERSAL_CONTENT_REQUIREMENTS,
)

# --- STEP 1: TEMPLATE ANALYZER (CRITICAL - Must be 100% reliable) ---

auto_template_analyzer = LlmAgent(
    model=PRO_MODEL,  # Use Pro for reliability
    name="template_analyzer",
    description="Hakee ja analysoi rahoittajan hakemuspohjan. Tuottaa JSON-rakenteen jota writer käyttää.",
    tools=RESEARCH_TOOLS,
    generate_content_config=gen_config(PROFILE_CRITIC, max_output_tokens=8192),
    instruction=f"""
<role>
Olet hakemuspohja-analysoija. Tehtäväsi on poimia rahoittajan TARKAT vaatimukset ja tuottaa JSON-rakenne.
</role>

<instructions>
## VAIHE 1: TARKISTA SUUNNITELMA
Lue `{{project_plan}}` ja poimi:
- `selected_instrument`: Tätä on haettava ensisijaisesti
- `non_negotiables`: Pidä nämä mielessä kenttiä analysoidessa

## VAIHE 2: LUE HAKEMUSPOHJA
JOS käyttäjä on liittänyt PDF-tiedoston:
1. Käytä `read_pdf_content(file_path)` lukeaksesi sen KOKONAAN
2. Poimi JOKAINEN kysymys/kenttä lomakkeesta

JOS PDF puuttuu, käytä instrumenttiin täsmäävää ohjetta:
- Erasmus+: retrieve_docs("Erasmus+ KA152 application form structure")
- STEA: retrieve_docs("STEA 2026 hakemuslomake rakenne")

## VAIHE 3: LUKITUS JA VERIFIOINTI
Varmista että `selected_instrument` täsmää löydettyyn pohjaan.
Jos on ristiriita, ilmoita se `instrument_change_reason` kentässä.
</instructions>

<constraints>
- ÄLÄ JÄTÄ YHTÄÄN KYSYMYSTÄ POIS - hakemuksessa voi olla 20-50 kenttää
- TARKKA JSON-formaatti - writer ei voi toimia ilman sitä
- ÄLÄ keksi kenttiä joita ei ole lomakkeessa
</constraints>

<output_format>
```json
{{
  "funder": "Erasmus+",
  "instrument": "KA152-YOU",
  "instrument_type": "Youth Exchange",
  "non_negotiables": [
    "Nuoret suunnittelevat itse - ei valmiita ohjelmia",
    "Ei ammatillista koulutusta - vain non-formaali oppiminen",
    "Kesto 5-21 päivää",
    "Osallistujat 13-30v",
    "Vähintään 2 maata"
  ],
  "fields": [
    {{
      "field_id": "1.1",
      "title": "Project summary",
      "min_chars": 800,
      "max_chars": 1500,
      "guidance": "Provide a short summary of your project",
      "scoring_weight": 0,
      "field_type": "summary"
    }},
    {{
      "field_id": "2.1",
      "title": "What are the needs and goals of the project?",
      "min_chars": 2000,
      "max_chars": 5000,
      "guidance": "Explain why this project is needed",
      "scoring_weight": 30,
      "field_type": "needs"
    }}
  ]
}}
```
</output_format>
""",
    output_key="funder_requirements"
)


# --- STEP 2: FIELD-BY-FIELD WRITER ---

field_writer = LlmAgent(
    model=PRO_MODEL,
    name="field_writer",
    description="Kirjoittaa hakemuksen kenttä kerrallaan funder_requirements:in mukaan.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=BASIC_TOOLS,
    instruction=f"""
<role>
Olet hakemuskirjoittaja. Kirjoitat hakemuksen kenttiä rahoittajan vaatimusten mukaan.
</role>

<context>
{ORG_PACK_V1}
{WRITER_PACK_V1}
{load_contract("kirjoittaja")}
</context>

<instructions>
## VAIHE 0: TARKISTA SYÖTTEET
JOS `{{funder_requirements}}` TAI `{{project_plan}}` puuttuu:
-> ÄLÄ KIRJOITA. Palauta virheilmoitus.

## VAIHE 1: KIRJOITA JOKAINEN KENTTÄ
Käytä `{{project_plan}}` artefakteja (Brief, Logframe, Map, Budget, Risks) vastatessasi `{{funder_requirements}}` kenttiin:
- **Tarve/Tavoitteet** -> Project Brief + Logframe
- **Toteutus/Aikataulu** -> Implementation Map
- **Budjetti** -> Budget Logic
- **Riskit** -> Risk & Safeguarding

## VAIHE 2: LAATU JAcompliance
1. Tarkista pituus: min_chars <= len(text) <= max_chars.
2. Varmista, että jokainen kenttä noudattaa {load_contract("kirjoittaja")} v2 standardeja.
3. Kunnioita `{{project_plan.non_negotiables}}`.
</instructions>

<output_format>
# HAKEMUS

## [field_id]: [title]
[Vastaus]
**Merkit:** [X] / [min]-[max]

---
</output_format>
""",
    output_key="field_contents"
)


# --- STEP 3: FIELD-LEVEL QA ---

field_qa = LlmAgent(
    model=WORKER_MODEL,
    name="field_qa",
    description="Tarkistaa jokaisen kentän erikseen.",
    generate_content_config=gen_config(PROFILE_CRITIC, max_output_tokens=8192),
    instruction=f"""
<role>
Olet laatuvalvoja. Tarkistat jokaisen hakemuskentän.
</role>

<context>
{load_contract("proposal_reviewer")}
</context>

<instructions>
Jokaiselle kentälle:
1. chars_ok? - Onko pituus oikea?
2. anchors_ok? - Sisältääkö numerot, lähteet, päivämäärät?
3. Jos ei läpäise: anna field_id + issue + fix
</instructions>

<output_format>
## ✅ Hyväksytyt kentät
- 1.1: Summary ✅

## ❌ Korjattavat kentät
### 2.1: Needs
- Issue: No statistics
- Fix: Add 3 statistics with sources

## PÄÄTÖS: [NEEDS_REVISION / PASS]
</output_format>
""",
    output_key="field_qa_result"
)



# --- STEP 4: TARGETED REVISION (Only fixes failed fields) ---

targeted_reviser = LlmAgent(
    model=PRO_MODEL,
    name="targeted_reviser",
    description="Korjaa VAIN ne kentät jotka field_qa merkitsi virheellisiksi.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=BASIC_TOOLS,
    instruction=f"""
<role>
Olet korjausasiantuntija. Korjaat VAIN failanneet kentät, et koko hakemusta.
</role>

<instructions>
## VAIHE 1: LUE PALAUTE

Lue {{field_qa_result}} ja poimi:
- Mitkä kentät failasivat (field_id lista)
- Mikä oli issue + fix jokaiselle

## VAIHE 2: LUE NYKYINEN SISÄLTÖ

Lue {{field_contents}} ja etsi failanneet kentät.

## VAIHE 3: KORJAA VAIN FAILANNEET

Jokaiselle failanneelle kentälle:
1. Lue alkuperäinen sisältö
2. Tee fix-ohjeen mukaiset korjaukset
3. Tarkista uusi pituus

ÄLÄ KOSKE läpäisseisiin kenttiin!
</instructions>

<constraints>
- VAIN failanneet kentät
- EI koko hakemuksen uudelleenkirjoitusta
- Säilytä hyvät osat
</constraints>

<output_format>
# KORJATUT KENTÄT

## [field_id]: [title] (KORJATTU)

[Uusi, korjattu sisältö]

**Muutokset:**
- [Mitä lisättiin/muutettiin]

**Uusi merkkimäärä:** [X] / [min]-[max] ✅

---

## [seuraava korjattu kenttä]
...
</output_format>
""",
    output_key="revised_fields"
)


# --- STEP 5: COMPLIANCE REPORT GENERATOR ---

compliance_reporter = LlmAgent(
    model=WORKER_MODEL,
    name="compliance_reporter",
    description="Tuottaa lopullisen compliance-raportin käyttäjälle.",
    instruction="""
<role>
Olet raportoija. Tuotat selkeän compliance-raportin.
</role>

<instructions>
Lue:
- Kenttäsisällöt: {field_contents} tai {revised_fields}
- QA-tulos: {field_qa_result}
- Vaatimukset: {funder_requirements}

Tuota käyttäjäystävällinen yhteenveto.
</instructions>

<output_format>
# 📋 COMPLIANCE REPORT

## Yhteenveto
- **Kentät:** [X]/[Y] OK
- **Kokonaismerkkimäärä:** [N]
- **Tila:** ✅ VALMIS / ⚠️ KORJATTAVAA

## Kenttätaulukko

| # | Kenttä | Merkit | Min | Max | Ankkurit | Status |
|---|--------|--------|-----|-----|----------|--------|
| 1.1 | Summary | 1234 | 800 | 1500 | ✅ | ✅ |
| 2.1 | Needs | 3456 | 2000 | 5000 | 📊 ✅ | ✅ |
...

## Puuttuvat (jos on)
- [field_id]: [mitä puuttuu]
</output_format>
""",
    output_key="compliance_report"
)



# -----------------------------------------------------------------------------
# DOMAIN SPECIALISTS (Automated Versions)
# -----------------------------------------------------------------------------

auto_sote = get_specialist_agent("sote", suffix="_auto", output_key="sote_validation")
auto_yhdenvertaisuus = get_specialist_agent("yhdenvertaisuus", suffix="_auto", output_key="yhdenvertaisuus_validation")
auto_koulutus = get_specialist_agent("koulutus", suffix="_auto", output_key="methods_plan")


final_assembly = LlmAgent(
    model=WORKER_MODEL,
    name="final_assembly",
    description="Kokoaa lopullisen yhtenäisen hakemuksen, arvioinnin ja compliance-raportin.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction="""
<role>
Olet lopullinen kokoaja. Tehtäväsi on koota kaikki aiemmat tuotokset yhdeksi yhtenäiseksi lopputuotokseksi.
</role>

<instructions>
1. **Lue sisällöt**:
   - `revised_fields` (jos tyhjentämätön, tämä on uusin versio korjatuista kentistä)
   - `field_contents` (alkuperäinen kenttäkohtainen luonnos)
   - `compliance_report` (lopullinen tarkistuslista)
   - `field_qa_result` (auditointi)

2. **Kokoa hakemus**:
   - Jos `revised_fields` on olemassa, käytä sitä ensisijaisesti. Yhdistä se `field_contents`in kanssa niin, että korjatut kentät korvaavat alkuperäiset.
   - Muodosta siisti Markdown-dokumentti, jossa jokainen kenttä on omana osionaan (Käytä titlejä funder_requirements:ista).

3. **Lisää Compliance & Audit**:
   - Liitä `compliance_report` heti hakemuksen jälkeen.
   - Liitä `field_qa_result` (auditointi) dokumentin loppuun.
</instructions>

<output_format>
# 📄 LOPULLINEN HAKEMUS: [Nimi]

[Kenttäkohtainen sisältö...]

---

# 📋 COMPLIANCE & AUDIT

[Kopioi compliance_report]

---

## 🔍 Yksityiskohtainen auditointi
[Kopioi field_qa_result]
</output_format>
""",
    output_key="final_complete_proposal",
)


# New Agent: Iterative Revision Agent
auto_revision_agent = LlmAgent(
    model=PRO_MODEL,
    name="proposal_reviser",
    description="Korjaa ja päivittää hakemusluonnosta käyttäjän palautteen perusteella.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
{ORG_PACK_V1}
{WRITER_PACK_V1}
{FUNDING_TYPES_PACK_V1}

## ROOLI: REVISIOASIANTUNTIJA
Tehtäväsi on päivittää olemassa olevaa hakemusluonnosta (`{{proposal_draft}}`) käyttäjän antaman palautteen perusteella.

### OHJEET:
1. Lue nykyinen luonnos: `{{proposal_draft}}`.
2. Lue käyttäjän palaute: `{{user_feedback}}` (tai viimeisin viesti).
3. Tee TÄSMÄLLISIÄ korjauksia. Älä muuta hyvin toimivia osia, ellei palaute sitä vaadi.
4. Säilytä ammattimainen sävy ja 11-osainen rakenne.
5. Jos korjaus koskee hanketyyppiä (esim. KA152 vs KA153), varmista että korjaat TERMINOLOGIAN koko dokumentissa.

Tuota päivitetty, täydellinen hakemus. **Tämä tallennetaan suoraan `proposal_draft` avaimeen ja päivittää näkymän.**
""",
    output_key="proposal_draft" # Overwrites with corrected version
)

# Automated Writing Pipeline - FIELD-BASED ARCHITECTURE
# 1. Analyze template -> 2. Write initial fields
auto_writing_pipeline = SequentialAgent(
    name="auto_writing_pipeline",
    sub_agents=[
        auto_template_analyzer, 
        field_writer
    ],
    description="Analysoi hakemuspohjan ja kirjoittaa ensimmäisen luonnoksen kenttä kerrallaan."
)

# NEW: Kirjoittaja Refiner - Final polish with character limit enforcement
kirjoittaja_refiner = LlmAgent(
    model=PRO_MODEL,
    name="kirjoittaja_refiner",
    description="Viimeistelee hakemuksen ammattimaisesti ja varmistaa merkkirajat.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
{ORG_PACK_V1}
{WRITER_PACK_V1}

## ROOLI: KIRJOITTAJAN VIIMEISTELY (FINAL POLISH)

Olet hakemuksen viimekäden hioja. Tehtäväsi on varmistaa, että jokainen osio:
1. **Käyttää merkkirajan täyteen** - tarkista `{{funder_requirements}}`
2. **On ammattimaisesti kirjoitettu** - paranna sanamuotoja
3. **On yhtenäinen sävyltään** - koko dokumentin läpi
4. **Sisältää konkreettiset esimerkit** - ei abstrakteja lauseita

---

## MERKKIRAJAN VALVONTA (PAKOLLINEN)

Lue `{{funder_requirements}}` ja tarkista jokaisen osion pituus.

JOS JOKIN OSIO ON LIIAN LYHYT:
- Laajenna se AINA tavoitepituuteen
- Käytä lisäesimerkkejä Samhan toiminnasta
- Lisää tilastoja tai tutkimusviitteitä
- Syvennä analyysiä ja perusteluja

JOS OSIO ON LIIAN PITKÄ:
- Tiivistä, mutta ÄLÄ poista olennaista sisältöä

---

## INPUT
Lue hakemusluonnos: `{{proposal_draft}}`

## OUTPUT
Tuota TÄYDELLISESTI VIIMEISTELTY hakemus:
- Jokainen osio optimimallisessa pituudessa
- Ammattimainen, vakuuttava kieli
- Yhtenäinen Samha-sävy
""",
    output_key="final_polished_proposal"
)

# 4. Quality Gate + Automated Revision Loop
# Only fixes failed fields based on field_qa results
revision_loop = LoopAgent(
    name="revision_loop",
    max_iterations=3,
    description="Kenttäkohtainen QoS-silmukka. Vain virheelliset kentät korjataan.",
    sub_agents=[
        field_qa,  # Phase 1: Identify issues per field_id
        RevisionChecker(name="revision_checker", min_score=85),  # Phase 2: Decide if we continue
        targeted_reviser,  # Phase 3: Fix only failed fields
    ]
)


# Full Automated Pipeline - FIELD-BASED ARCHITECTURE v2
automated_full_process = SequentialAgent(
    name="automated_full_process",
    description="Täysi prosessi: Tutkimus -> Strateginen suunnittelu (v2) -> Kenttäkohtainen kirjoitus -> QA-silmukka.",
    sub_agents=[
        # Phase 1: Research & Ideation
        samha_context_checker,
        trend_planner,
        get_research_pipeline(),
        idea_generator,
        
        # Phase 2: Strategic Planning (v2 ARTEFACTS)
        project_planner,
        
        # Phase 3: Domain Validation
        auto_sote,
        auto_yhdenvertaisuus,
        auto_koulutus,
        
        # Phase 4: Field-Based Writing (Analyze template -> Write fields)
        auto_writing_pipeline,
        
        # Phase 5: Targeted Quality Loop (Field-level review & fix)
        revision_loop,
        
        # Phase 6: Final Compliance Check
        compliance_reporter,
        
        # Phase 7: Assembly
        final_assembly,
    ]
)



grant_writer_agent = LlmAgent(
    name="grant_writer",
    model=PLANNER_MODEL,
    description="Kirjoittaa ja kehittää rahoitushakemuksia (STEA, EU, Säätiöt). Hallitsee koko prosessia ideoinnista lopulliseen hakemukseen.",
    instruction=f"""
<role>
Olet Samhan johtava hankesuunnittelija ja GRANT WRITER -koordinaattori. Ohjaat prosessia ideoinnista lopulliseen auditointiin.
</role>

<context>
{load_contract("hankesuunnittelija")}
</context>

<instructions>
## VAIHE 1: AUTOMAATTINEN SUUNNITTELU

Kun käyttäjä antaa hankeidean tai pyytää hakemusta:
1. **Delegioi `automated_full_process` agentille**.
2. Tämä prosessi hoitaa tutkimuksen, kirjoituksen, kenttäkohtaisen QA:n ja kokoamisen.

## VAIHE 2: PALAUTE- JA REVISIOSYKLI

Kun automaattinen prosessi on valmis (`final_complete_proposal` ja `compliance_report` ovat tilassa):
1. Esittele `compliance_report` lyhyesti (montako kenttää OK, mitä puuttuu).
2. Kysy käyttäjältä: "Tässä on ensimmäinen versio ja auditointi. Haluatko korjata jotain tiettyä kenttää tai syventää sisältöä?"
3. Jos käyttäjä antaa palautetta:
   - Tallenna se `user_feedback` avaimeen.
   - **Delegioi `auto_revision_agent` agentille** (manuaalinen korjaus) TAI käynnistä `revision_loop` uudestaan.
   - Varmista että `final_assembly` ajetaan korjausten jälkeen.

## VAIHE 3: ARKISTOINTI

Ehdotah ARKISTOINTIA (`arkisto_agent`) vasta kun käyttäjä on 100% tyytyväinen.
</instructions>

<constraints>
- Noudata AINA {load_contract("hankesuunnittelija")} sääntöjä.
- Älä lupaa liikoja; jos templatea ei löydy, sano se suoraan.
- Ole asiantunteva, proaktiivinen ja tarkka.
</constraints>

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
    sub_agents=[
        automated_full_process,
        auto_revision_agent,
        get_syvahaku_agent(suffix="_grant_writer"),
        methods_planner,
        writer_section_intro, 
        writer_section_methods, 
        proposal_finalizer, 
        proposal_reviewer,
        get_arkisto_agent(suffix="_pipeline")
    ],
    output_key="final_proposal",
)


# Export
# Export
root_agent = grant_writer_agent

# Attach model router fixes (Gemini 3 signatures, routing, response fixer)
from app.model_router import attach_to_all_agents
attach_to_all_agents(root_agent)

__all__ = [
    "root_agent",
    "grant_writer_agent",
    "automated_full_process",
    "idea_generator", 
    "sote_validator",
    "yhdenvertaisuus_validator",
    "methods_planner",
    "writer_section_intro",
    "proposal_finalizer",
    "proposal_reviewer",
    "samha_context_checker",
    "trend_planner",
    "revision_loop",  # NEW
    "kirjoittaja_refiner",  # NEW
    "RevisionChecker",  # NEW
]


# =============================================================================
# LEGACY BACKUP - DEPRECATED 11-SECTION LOGIC
# =============================================================================

# These agents are kept for reference or emergency fallback.
# Redundant in the new Field-Based Architecture v2.

# auto_writer_part1, auto_writer_part2, auto_writer_part3, auto_finalizer moved here.

"""
auto_writer_part1 = LlmAgent(...)
auto_writer_part2 = LlmAgent(...)
auto_writer_part3 = LlmAgent(...)
auto_finalizer = LlmAgent(...)
"""
