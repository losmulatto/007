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
from google.genai import types as genai_types
from google.adk.agents import LlmAgent, SequentialAgent
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
trend_researcher = LlmAgent(
    model=WORKER_MODEL,
    name="trend_researcher",
    description="Tutkii ajankohtaiset trendit, rahoittajaprioriteetit ja tarpeet.",
    instruction=f"""
## SINUN ROOLISI: TRENDIANALYYTIKKO
{CRITICAL_REFLECTION_PACK_V1}

Tutki hankeideointia varten:
1. Ajankohtaiset trendit ja tutkimukset aiheesta.
2. Soveltuvat rahoituskanavat (Kansalliset sote-avustukset, EU-ohjelmat, säätiöt tai kunnalliset avustukset).
3. Kohderyhmän tarpeet ja haasteet.
4. Innovatiiviset lähestymistavat muualta.

### TEHTÄVÄ
Käytä työkaluja (`search_verified_sources`, `search_news`, `search_web`, `retrieve_docs`) löytääksesi:
- Uusimmat tutkimukset ja tilastot.
- Rahoitusmahdollisuudet (etsi parhaiten sopivat).
- Onnistuneet esimerkit vastaavista hankkeista.
- Aukot nykyisessä palvelutarjonnassa.

## EVIDENSSIVAATIMUS (PAKOLLINEN)
Jos väität mitään faktuaalista (vuosi, %, määrä, "uusin"), näytä heti perässä lähde:
- **Otsikko**: ...
- **URL**: https://...
- **Todiste**: 1–2 lausetta mitä sivu sanoo ja mihin kohtaan hanketta se vaikuttaa.

**Älä käytä alaviitteitä. Älä keksi lukuja (Numeric Integrity).** Jos et löydä dataa työkaluilla, kirjoita "tieto puuttuu" ja listaa mitä pitää hakea.

### OUTPUT
Tuota tiivistelmä Markdown-muodossa, jossa jokaisessa osiossa on vähintään yksi todiste.
""",
    tools=RESEARCH_TOOLS,
    output_key="trend_analysis",
)


# Step 2: Idea Generation
idea_generator = LlmAgent(
    model=PLANNER_MODEL,
    name="idea_generator",
    description="Ideoi innovatiivisia hankekonsepteja trendianalyysin pohjalta.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
## SINUN ROOLISI: HANKEIDEOIJA
{CRITICAL_REFLECTION_PACK_V1}
{FUNDING_TYPES_PACK_V1}

## PÄÄTÖSTEN LUKITUS
Valitse 1 "suositeltu konsepti" ja lukitse nämä kentät:
- **selected_instrument**: stea / erasmus+ / säätiö / kunta / muu
- **non_negotiables**: 5 sääntöä joita ei rikota (esim. "ei kansainvälisiä matkoja stea:ssa", "ei hoitoa, vain tuki/ohjaus")
Jatkovaiheissa et saa muuttaa instrumenttia ilman että kerrot "instrument_change_reason".

Lue trendianalyysi: `{{trend_analysis}}`

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
{CRITICAL_REFLECTION_PACK_V1}

Lue hankeideat: `{{project_ideas}}`

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
{CRITICAL_REFLECTION_PACK_V1}

Lue hankeideat: `{{project_ideas}}`
Lue SOTE-arviointi: `{{sote_validation}}`

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
{CRITICAL_REFLECTION_PACK_V1}

Lue:
- Hankeideat: `{{project_ideas}}`
- SOTE-arviointi: `{{sote_validation}}`
- Yhdenvertaisuusarviointi: `{{yhdenvertaisuus_validation}}`

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


# Step 6: Proposal Writing
proposal_writer = LlmAgent(
    model=PLANNER_MODEL,
    name="proposal_writer",
    description="Kirjoittaa hakemusluonnoksen.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction=f"""
## SINUN ROOLISI: KIRJOITTAJA (HAKEMUS)
{CRITICAL_REFLECTION_PACK_V1}
{FUNDING_TYPES_PACK_V1}

Lue kaikki aiemmat vaiheet:
- Trendianalyysi: `{{trend_analysis}}`
- Hankeideat: `{{project_ideas}}`
- SOTE-arviointi: `{{sote_validation}}`
- Yhdenvertaisuusarviointi: `{{yhdenvertaisuus_validation}}`
- Menetelmäsuunnitelma: `{{methods_plan}}`

### TEHTÄVÄ
Kirjoita TÄYSI hakemusluonnos valitulle rahoittajalle. 
**Noudata FUNDING_TYPES_PACK_V1:n sääntöjä orjallisesti.**

## NUMERIC INTEGRITY
Et saa kirjoittaa yhtään numeroa (€, %, osallistujamäärä, vuodet) ellei se ole:
a) Annettu inputissa, tai
b) Löydetty työkaluilla ja listattu "lähteet"-osiossa.
Muuten kirjoita "tieto puuttuu" ja tee paikka täydennettäväksi.

### OUTPUT
Tuota täysi hakemus, joka sisältää kaikki tarvittavat osiot. Lisää loppuun "Käytetyt lähteet" -osio (ilman alaviitteitä).
""" ,
    tools=BASIC_TOOLS,
    output_key="proposal_draft",
)


# Step 7: Proposal Review
proposal_reviewer = LlmAgent(
    model=PLANNER_MODEL,
    name="proposal_reviewer",
    generate_content_config=CRITIC_CONFIG,
    tools=RESEARCH_TOOLS,
    description="Arvioi hakemusluonnosta ja antaa palautetta kriittisesti hyödyntäen virallisia oppaita.",
    instruction=f"""
{ORG_PACK_V1}
{RADICAL_AUDITOR_PACK_V1}
{QA_PORT_PACK_V1}
{GOLD_FAILURE_PACK_V1}
{FUNDING_TYPES_PACK_V1}

## SINUN ROOLISI: THE ENFORCER (RADICAL AUDITOR)

Lue koko prosessin kulku ja erityisesti hakemusluonnos: `{{proposal_draft}}`

## AUDIT-PROTOKOLLA (PAKOLLINEN JÄRJESTYS)
1. **Hae ohjeet**: Hae ensin virallinen ohjelmaopas tai rahoittajan ohje (`retrieve_docs` tai `search_verified_sources`) ja listaa URL:t.
2. **Faktojen tarkistus**: Poimi hakemuksesta 10 kriittistä väitettä (instrumentti, kohderyhmä, toiminta, mittarit, budjetti-logiikka).
3. **Vastakkainasettelu**: Jokaiselle väitteelle: Status OK/EI OK + Lähde-URL + korjausohje.

### ARVIOINTI-MODUS
1. **Aloita DESTRUCTION PHASE**: Listaa 3 kriittistä syytä, miksi tämä hanke on tällä hetkellä epäonnistuminen.
2. **Pisteytys**: Käytä 0-100 asteikkoa (61+ = Läpäisy).
3. **Sektoripoliisi**: Tarkista rahoitusinstrumentin mukaisuus (FUNDING_TYPES_PACK_V1).

### OUTPUT FORMAT
```markdown
# Hakemusarviointi: RADICAL AUDIT REPORT

## Destructive Analysis (Red Team)
...

## Kokonaispisteet: XX / 100 

## Väitteiden auditointi (10 kpl)
- [Väite]: [Status] | [URL] | [Ohje]

## ROADMAP TO 81+ (Actionable Remediation)
...
```
""" ,
    output_key="proposal_review",
)


# =============================================================================
# MAIN WORKFLOW
# =============================================================================

hankesuunnittelija_pipeline = SequentialAgent(
    name="hankesuunnittelija_pipeline",
    description="Täysi hankesuunnitteluprosessi: trendianalyysi → ideointi → validointi → menetelmät → hakemus → arviointi",
    sub_agents=[
        trend_researcher,
        idea_generator,
        sote_validator,
        yhdenvertaisuus_validator,
        methods_planner,
        proposal_writer,
        proposal_reviewer,
    ],
)


hankesuunnittelija_agent = LlmAgent(
    name="hankesuunnittelija",
    model=WORKER_MODEL,
    description="Ideoi ja kehittää uusia hankeideoita tutkimusten perusteella. Ketjuttaa kaikkien asiantuntijoiden läpi: tutkimus → sote → yhdenvertaisuus → menetelmät → hakemus.",
    instruction=f"""
## SINUN ROOLISI: HANKESUUNNITTELIJA

Olet Samhan hankesuunnittelun pääkoordinaattori. Autat ideoimaan ja kehittämään uusia hankeideoita.

### PROSESSI

Kun käyttäjä pyytää hankeideoita, käynnistät automaattisen ketjun:

1. **Trendianalyysi** → Tutkii trendit ja rahoittajaprioriteetit
2. **Ideointi** → Generoi 3-5 hankekonseptia
3. **SOTE-validointi** → Arvioi sote-näkökulmasta
4. **Yhdenvertaisuus-validointi** → Arvioi antirasisminäkökulmasta
5. **Menetelmäsuunnittelu** → Suunnittelee konkreettiset toiminnot
6. **Hakemuskirjoitus** → Kirjoittaa täyden hakemuksen
7. **QA-arviointi** → Arvioi ja antaa palautetta

### MILLOIN KÄYTETÄÄN

- "Ideoi uusi hanke nuorten mielenterveydestä"
- "Kehitä antirasismihanke Erasmus+:lle"
- "Suunnittele STEA-hanke vertaistukiryhmille"

### OHJEET

1. Kysy tarvittaessa tarkentavia kysymyksiä
2. Käynnistä `hankesuunnittelija_pipeline`
3. Esitä lopputulos käyttäjälle
4. Kysy haluaako käyttäjä arkistoida hakemuksen

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
    sub_agents=[hankesuunnittelija_pipeline],
    output_key="final_proposal",
)


# Export
root_agent = hankesuunnittelija_agent
