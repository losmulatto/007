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
           ↓
    [1] trend_researcher → tutkii trendit ja rahoittajaprioriteetit
           ↓
    [2] idea_generator → ideoi 3-5 hankekonseptia
           ↓
    [3] sote_validator → arvioi sote-näkökulmasta
           ↓
    [4] yhdenvertaisuus_validator → arvioi yhdenvertaisuusnäkökulmasta
           ↓
    [5] methods_planner → suunnittelee menetelmät
           ↓
    [6] proposal_writer → kirjoittaa hakemuksen
           ↓
    [7] proposal_reviewer → arvioi ja antaa palautetta
           ↓
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
    CRITICAL_REFLECTION_PACK_V1,
    FUNDING_TYPES_PACK_V1,
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
from app.deep_search import get_research_pipeline, syvahaku_agent
from app.ammattilaiset import arkisto_agent


# =============================================================================
# LOOP CONTROL & CUSTOM AGENTS
# =============================================================================


# =============================================================================
# CONFIGURATION
# =============================================================================

WORKER_MODEL = "gemini-3-flash-preview"
PLANNER_MODEL = "gemini-3-pro-preview"

LONG_OUTPUT_CONFIG = genai_types.GenerateContentConfig(
    max_output_tokens=16384,
)

CRITIC_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.2,
    max_output_tokens=8192,
)


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
{load_contract("tutkija")}
{ORG_PACK_V1}

## TARKISTUSVAIHE (PHASE 0)
Tehtäväsi on varmistaa, että tuleva trenditutkimus kohdistuu oikein.

Tarkista (`retrieve_docs`) tai lue ORG_PACK:
1. **Kohderyhmät**: Keitä Samha palvelee? (Maahanmuuttajat, syrjäytymisriskissä olevat)
2. **Arvot**: Onko hanke linjassa matalan kynnyksen ja kulttuurisensitiivisyyden kanssa?

Jos käyttäjän idea on selvästi ristiriidassa (esim. "Vain kantasuomalaisille"), ilmoita siitä.
Muuten, anna lupa jatkaa tutkimukseen ja KIRJAA YLÖS konteksti seuraavaa vaihetta varten.
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
You are a generic research planner.
OUTPUT LANGUAGE: FINNISH.
Your goal is to create a RESEARCH PLAN to investigate trends, funding, and needs for the user's project idea.

CONTEXT FROM PHASE 0:
{{samha_context}}

**TASK**
Create a 5-point research plan to:
1. Identify current trends and statistics.
2. Find suitable funding instruments (STEA, EU, Foundations).
3. Analyze target group needs (specifically Samha's groups).
4. Look for benchmarks/innovations.

**OUTPUT FORMAT**
Bulleted list where each line starts with `[RESEARCH]`.
DO NOT ask for user approval. This is an automated pipeline.
""",
    output_key="research_plan",
)



# Step 2: Idea Generation
idea_generator = LlmAgent(
    model=PLANNER_MODEL,
    name="idea_generator",
    description="Ideoi innovatiivisia hankekonsepteja trendianalyysin pohjalta.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
## SINUN ROOLISI: HANKEIDEOIJA
{load_contract("hankesuunnittelija")}
{CRITICAL_REFLECTION_PACK_V1}
{FUNDING_TYPES_PACK_V1}

## PÄÄTÖSTEN LUKITUS
Valitse 1 "suositeltu konsepti" ja lukitse nämä kentät:
- **selected_instrument**: stea / erasmus+ / säätiö / kunta / muu
- **non_negotiables**: 5 sääntöä joita ei rikota (esim. "ei kansainvälisiä matkoja stea:ssa", "ei hoitoa, vain tuki/ohjaus")
Jatkovaiheissa et saa muuttaa instrumenttia ilman että kerrot "instrument_change_reason".

Lue trendianalyysi: `{{final_cited_report}}`

### TEHTÄVÄ
Ideoi 3-5 innovatiivista hankekonseptia, jotka vastaavat trendejä. 
**TÄRKEÄÄ: RAHOITUSLOGIIKKA**. Älä sekoita kriteerejä.

### OUTPUT: Jokaisesta ideasta
```markdown
## Konsepti [N]: [Nimi]
**Rahoitusinstrumentti:** [STEA / Erasmus+ / Muu] - PERUSTELE LUKITTU VALINTA.
**Ongelma & Ratkaisu:** ...
**Kohderyhmä & Menetelmät:** ...
**Riskit:** ...
```

### LOPUKSI
Suosittele parasta konseptia jatkokehitykseen.
""" ,
    tools=BASIC_TOOLS,
    output_key="project_ideas",
)


# Step 3: SOTE Validation
sote_validator = LlmAgent(
    model=WORKER_MODEL,
    name="sote_validator",
    description="Arvioi hankeidean sote-näkökulmasta.",
    instruction=f"""
## SINUN ROOLISI: SOTE-ASIANTUNTIJA (VALIDOINTI)
{load_contract("sote")}
{CRITICAL_REFLECTION_PACK_V1}

Lue hankeideat: `{{project_ideas}}`
Lue edellinen auditointipalautte (jos on): `{{proposal_review?}}`

### TEHTÄVÄ

Arvioi SUOSITELTU hankeidea SOTE-näkökulmasta:

1. **Mielenterveys**: Miten hanke tukee mielenterveyttä?
2. **Kynnykset**: Puretaanko osallistumisen esteitä?
3. **Hyvinvointi**: Miten edistää kokonaisvaltaista hyvinvointia?
4. **Turvallisuus**: Onko kohderyhmälle turvallinen?
5. **Rajapinnat**: Onko toiminta selkeästi erotettu lääketieteellisestä hoidosta?

### OUTPUT
Tuota arviointi seuraavalla rakenteella:
1. **Sektorin tarkistus**: Onko hanke sote-alueella vai nuorisotyötä?
2. **Kynnykset ja Inkluusio**: ...
3. **Turvallisuus**: ...
4. **Varoitusmerkit**: Jos löydät "hoito/terapia"-termejä, huomauta tästä.

Lopuksi anna **Sote-status**: [Puhas nuorisotyö / Sote-rajapinta / Sote-hanke].
""" ,
    tools=BASIC_TOOLS,
    output_key="sote_validation",
)


# Step 4: Equality Validation
yhdenvertaisuus_validator = LlmAgent(
    model=WORKER_MODEL,
    name="yhdenvertaisuus_validator",
    description="Arvioi hankeidean yhdenvertaisuusnäkökulmasta.",
    instruction=f"""
## SINUN ROOLISI: YHDENVERTAISUUS-ASIANTUNTIJA (VALIDOINTI)
{load_contract("yhdenvertaisuus")}
{CRITICAL_REFLECTION_PACK_V1}

Lue hankeideat: `{{project_ideas}}`
Lue SOTE-arviointi: `{{sote_validation}}`
Lue edellinen auditointipalautte (jos on): `{{proposal_review?}}`

### TEHTÄVÄ

Arvioi SUOSITELTU hankeidea yhdenvertaisuusnäkökulmasta:

1. **Saavutettavuus**: Onko kaikille saavutettava?
2. **Inkluusio**: Huomioidaanko erilaiset taustat?
3. **Antirasismi**: Edistääkö rakenteellista yhdenvertaisuutta?
4. **Intersektionaalisuus**: Huomioidaanko risteävät identiteetit?
5. **Osallisuus**: Ovatko nuoret suunnittelijoita vai kohteita?

### OUTPUT
Tuota arviointi seuraavalla rakenteella:
1. **Yhdenvertaisuusbloqqi**: Saavutettavuus, inkluusio, antirasismi.
2. **Osallisuusaste**: 1-5 (ovatko nuoret tekijöitä vai kohteita).
3. **Parannusehdotukset**: ...

Lopuksi anna **Yhdenvertaisuus-status**: [Erinomainen / Kehitettävää / Puutteellinen].
""" ,
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
## SINUN ROOLISI: KOULUTUSSUUNNITTELIJA (MENETELMÄT)
{load_contract("koulutus")}
{CRITICAL_REFLECTION_PACK_V1}

Lue:
- Hankeideat: `{{project_ideas}}`
- SOTE-arviointi: `{{sote_validation}}`
- Yhdenvertaisuusarviointi: `{{yhdenvertaisuus_validation}}`
- Edellinen auditointipalautte (jos on): `{{proposal_review?}}`

### TEHTÄVÄ

Suunnittele hankkeen konkreettiset menetelmät ja toiminnot. 
**Tärkeää**: Jos hanke on Erasmus+, menetelmien on oltava non-formaalia oppimista. Jos se on STEA, niiden on oltava sosiaalista tukea/neuvontaa.

1. **Toimenpiteet**: Mitä tehdään vuosittain?
2. **Menetelmät**: Millaisia osallistavia menetelmiä käytetään?
3. **Materiaalit**: Mitä tuotetaan?
4. **Koulutukset**: Mitä koulutuksia järjestetään?
5. **Aikataulu**: Milloin mitäkin tapahtuu?

### OUTPUT
Tuota menetelmäsuunnitelma:
- **Menetelmäyhteenveto**: (non-formaali oppiminen vs. sosiaalinen tuki).
- **Vuosi 1 - Toiminnot**: ...
- **Mittarit**: Miten onnistumista mitataan?
- **Resurssit**: Mitä tarvitaan?
""" ,
    tools=BASIC_TOOLS,
    output_key="methods_plan",
)


# Step 6: Proposal Writing (Phase A: Needs & Context)
writer_section_intro = LlmAgent(
    model=PLANNER_MODEL,
    name="writer_section_intro",
    description="Kirjoittaa hakemuksen tarveperustelut ja taustatiedoat.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
## ROOLI: KIRJOITTAJA (OSA 1: TARVE & TAUSTA)
{load_contract("kirjoittaja")}

Lue:
- Trendianalyysi: `{{final_cited_report}}`
- Hankeideat: `{{project_ideas}}`
- Edellinen auditointipalautte (jos on): `{{proposal_review?}}`

### KORJAUSTILA (REVISION MODE) - TÄRKEÄ!
Jos kontekstista löytyy aiempi `{{proposal_review}}` ja `{{proposal_section_intro}}`:
1. **Lue kritiikki**: Katso mitä `proposal_review` vaatii korjaamaan tässä osiossa.
2. **Korjaa**: Tee vaaditut muutokset (esim. "tarkenna kohderyhmää", "lisää statustietoa").
3. **Raportoi**: Listaa vastauksen alkuun: "Korjattu palautteen perusteella: [lista muutoksista]".

### TEHTÄVÄ
Kirjoita hakemuksen alkuosa:
1. **Hankkeen nimi ja lyhyt kuvaus**.
2. **Tarve ja tausta**: Miksi hanke tarvitaan nyt? Käytä trendianalyysin faktoja.
3. **Kohderyhmä**: Ketä hanke auttaa?

**KIRJOITA ERITTÄIN YKSITYISKOHTAISESTI JA PITKÄÄN.** Älä tiivistä.

### OUTPUT
Tuota Markdown-sisältöä vain näille osioille.
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
## ROOLI: KIRJOITTAJA (OSA 2: TOTEUTUS & MENETELMÄT)
{load_contract("kirjoittaja")}

Lue:
- Menetelmäsuunnitelma: `{{methods_plan}}`
- Hankeideat: `{{project_ideas}}`
- SOTE & Yhdenvertaisuus: `{{sote_validation}}`, `{{yhdenvertaisuus_validation}}`
- Edellinen auditointipalautte (jos on): `{{proposal_review?}}`

### KORJAUSTILA (REVISION MODE) - TÄRKEÄ!
Jos kontekstista löytyy aiempi `{{proposal_review}}` ja `{{proposal_section_methods}}`:
1. **Lue kritiikki**: Etsi palautteesta menetelmiin liittyvät huomiot.
2. **Korjaa**: Muokkaa toimintoja tai resursointia palautteen mukaan.
3. **Raportoi**: Listaa vastauksen alkuun: "Korjattu palautteen perusteella: [lista]".

### TEHTÄVÄ
Kirjoita hakemuksen ydin:
1. **Tavoitteet**: Mitä halutaan saavuttaa (SMART)?
2. **Toiminnot ja menetelmät**: Mitä hanke tekee käytännössä? Kirjoita auki jokainen työpaja ja menetelmä.
3. **Resurssit**: Kuka tekee ja mitä tarvitaan?

**KIRJOITA ERITTÄIN YKSITYISKOHTAISESTI JA PITKÄÄN.** Älä tiivistä.

### OUTPUT
Tuota Markdown-sisältöä vain näille osioille.
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
## ROOLI: KIRJOITTAJA (OSA 3: VAIKUTTAVUUS & KOOSTE)
{load_contract("kirjoittaja")}

Lue:
- Intro: `{{proposal_section_intro}}`
- Methods: `{{proposal_section_methods}}`
- Edellinen auditointipalautte (jos on): `{{proposal_review?}}`

### KORJAUSTILA (FINAL CHECK)
Jos kontekstista löytyy aiempi `{{proposal_review}}`:
- Varmista, että kaikki "ROADMAP TO 85+" -kohdat on huomioitu.
- Jos jotain puuttuu, lisää se nyt.

### TEHTÄVÄ
Viimeistele hakemus:
1. **Tulokset ja vaikuttavuus**: Mitä jää jäljelle? Miten toiminta jatkuu?
2. **Koostaminen**: Yhdistä aiemmat osat yhdeksi sujuvaksi kokonaisuudeksi.
3. **Lähdeluettelo**: Listaa kaikki trendianalyysissä ja kirjoittajilla käytetyt lähteet.

**VARMISTA ETTÄ LOPPUTULOS ON TÄYDELLINEN, AMMATTIMAINEN HAKEMUS.**

### OUTPUT
Tuota täysi hakemusluonnos, joka yhdistää kaikki osat.
""",
    tools=BASIC_TOOLS,
    output_key="proposal_draft",
)


# Step 9: Proposal Review (Dynamic Criteria Discovery)
proposal_reviewer = LlmAgent(
    model=PLANNER_MODEL,
    name="proposal_reviewer",
    generate_content_config=CRITIC_CONFIG,
    tools=RESEARCH_TOOLS,
    description="Etsii rahoittajakohtaiset kriteerit ja arvioi hakemuksen niiden perusteella.",
    instruction=f"""
{ORG_PACK_V1}
{RADICAL_AUDITOR_PACK_V1}
{QA_PORT_PACK_V1}
{GOLD_FAILURE_PACK_V1}
{FUNDING_TYPES_PACK_V1}

## SINUN ROOLISI: DYNAMIC AUDITOR (THE ENFORCER)
{load_contract("proposal_reviewer")}

Lue hakemusluonnos: `{{proposal_draft}}`

## VAIHE 1: KRITEERIEN ETSINTÄ (PAKOLLINEN)
Sinun on ensin haettava työkaluilla (`retrieve_docs` tai `search_web`) **juuri tämän haun kriteerit**. 
Esimerkkejä:
- Jos hakemus on STEA-hanke -> "STEA 2026 kriteerit ja hakuohjeet"
- Jos Erasmus+ -> "Erasmus+ Programme Guide 2025 quality criteria"
- Jos Säätiö -> Etsi kyseisen säätiön hakuohjeet.

Listaa löytyneet lähteet (URL tai doc nimi).

## VAIHE 2: AUDITOINTI
Arvioi hakemus löytämiesi spesifien sääntöjen perusteella. 
Älä käytä yleistä kaavaa, jos löydät tarkempia ohjeita.

### ARVIOINTI-MODUS
1. **DESTRUCTION PHASE**: Listaa 3 kriittistä syytä, miksi tämä hanke on tällä hetkellä epäonnistuminen löydettyjen kriteerien valossa.
2. **Pisteytys**: Käytä 0-100 asteikkoa (Kokonaispisteet: XX / 100). **THRESHOLD 85/100**.
3. **Veroitus**: Jos pisteet ovat alle 85, kerro TÄSMÄLLEEN mitä pitää kirjoittaa lisää tai korjata seuraavalla kierroksella.

### OUTPUT FORMAT
```markdown
# Hakemusarviointi: DYNAMIC AUDIT REPORT
**Löydetyt kriteerilähteet:** [Lista]

## Destructive Analysis
...

## Kokonaispisteet: XX / 100 

## Väitteiden auditointi (10 kpl)
...

## ROADMAP TO 85+ (Korjausohjeet seuraavalle kierrokselle)
...
```
""" ,
    output_key="proposal_review",
)


from app.ammattilaiset import get_arkisto_agent, get_specialist_agent
from google.adk.agents import SequentialAgent

# Fresh instances for the automated pipeline to avoid parentage conflicts
# with the manual coordinator's sub_agents.
auto_intro = get_specialist_agent("kirjoittaja", suffix="_auto_intro", output_key="proposal_section_intro")
auto_methods = get_specialist_agent("kirjoittaja", suffix="_auto_methods", output_key="proposal_section_methods")
auto_finalizer = get_specialist_agent("kirjoittaja", suffix="_auto_finalizer", output_key="proposal_draft")
auto_sote = get_specialist_agent("sote", suffix="_auto", output_key="sote_validation")
auto_yhdenvertaisuus = get_specialist_agent("yhdenvertaisuus", suffix="_auto", output_key="yhdenvertaisuus_validation")
auto_koulutus = get_specialist_agent("koulutus", suffix="_auto", output_key="methods_plan")

# Update factory to handle reviewer or instantiate manually
auto_reviewer = LlmAgent(
    model=PLANNER_MODEL,
    name="proposal_reviewer_auto",
    generate_content_config=CRITIC_CONFIG,
    tools=RESEARCH_TOOLS,
    description="Etsii rahoittajakohtaiset kriteerit ja arvioi hakemuksen niiden perusteella.",
    instruction=proposal_reviewer.instruction 
)

# Automated Writing Pipeline
auto_writing_pipeline = SequentialAgent(
    name="auto_writing_pipeline",
    sub_agents=[auto_intro, auto_methods, auto_finalizer],
    description="Automated 3-phase writing process."
)

# Full Automated Pipeline
automated_full_process = SequentialAgent(
    name="automated_full_process",
    description="Täysi automaattinen hankesuunnitteluprosessi tutkimuksesta arviointiin.",
    sub_agents=[
        samha_context_checker, # This might still conflict if shared... I'll use a factory if I need to.
        trend_planner,
        get_research_pipeline(),
        idea_generator,
        auto_sote,
        auto_yhdenvertaisuus,
        auto_koulutus,
        auto_writing_pipeline,
        auto_reviewer
    ]
)

grant_writer_agent = LlmAgent(
    name="grant_writer",
    model=PLANNER_MODEL,
    description="Kirjoittaa ja kehittää rahoitushakemuksia (STEA, EU, Säätiöt). Hallitsee koko prosessia ideoinnista lopulliseen hakemukseen.",
    instruction=f"""
## SINUN ROOLISI: GRANT WRITER (HANKESUUNNITTELUN KOORDINAATTORI)
{load_contract("hankesuunnittelija")}

Olet Samhan johtava hankesuunnittelija ja rahoitusasiantuntija. Ohjaat projektia vaihe vaiheelta.

### PROSESSI (AUTOMAATTINEN ALOITUS)

Kun käyttäjä pyytää aloittamaan uuden hakemuksen tai ideoimaan hanketta ("Suunnittele hanke...", "Aloitetaan haku..."), 
**DELEGOI VÄLITTÖMÄSTI `automated_full_process` agentille**. Se hoitaa koko ketjun kerralla.

### PAKOLLINEN MITATTAVUUS (TARVE & TAVOITTEET)
Jos käyttäjä pyytää "tarve ja tavoitteet" tai vain "tavoitteet":
- Kirjoita **vähintään 3 mitattavaa tavoitetta numeroilla** (esim. osallistujamäärä, työpajojen määrä, %-osuus).
- Käytä sanaa **"Tavoite"** jokaisessa kohdassa.

### MANUAALINEN / KORJAAVA KONTROLLI
Jos käyttäjä pyytää vain yhtä osiota tai haluaa PALATA aiempaan vaiheeseen:
1. **Palaa vaiheeseen X** -> Delegoi suoraan kyseiselle agentille (lista alla).
2. **Korjaa X palautteen perusteella** -> Delegoi kyseiselle agentille.

### SUB-AGENTS (MANUAALISEEN KÄYTTÖÖN)
- `methods_planner`: Toiminta ja menetelmät.
- `writer_section_intro`: Taustat ja tarpeet.
- `writer_section_methods`: Toiminnot ja resurssit.
- `proposal_finalizer`: Vaikuttavuus ja koonti.

### ARKISTOINTI
- Kun hakemus on valmis, ehdota tallennusta: "Arkistoi tämä".

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
    sub_agents=[
        automated_full_process,
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
root_agent = grant_writer_agent

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
]
