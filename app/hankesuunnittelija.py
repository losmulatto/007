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
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import google_search
from google.genai import types as genai_types


# =============================================================================
# CONFIGURATION
# =============================================================================

WORKER_MODEL = "gemini-2.5-flash"
PLANNER_MODEL = "gemini-2.5-pro"

LONG_OUTPUT_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.7,
    max_output_tokens=16384,
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

Tutkii hankeideointia varten:
1. Ajankohtaiset trendit ja tutkimukset aiheesta
2. STEA:n ja EU:n rahoitusprioriteetit
3. Kohderyhmän tarpeet ja haasteet
4. Innovatiiviset lähestymistavat muualta

### TEHTÄVÄ

Käytä `google_search` löytääksesi:
- Uusimmat tutkimukset ja tilastot
- Rahoittajien painopistealueet (STEA, Erasmus+)
- Onnistuneet esimerkit vastaavista hankkeista
- Aukot nykyisessä palvelutarjonnassa

### OUTPUT

Tuota tiivistelmä:
```markdown
# Trendianalyysi: [Aihe]

## Ajankohtaiset trendit
- ...

## Rahoittajaprioriteetit
- STEA: ...
- Erasmus+: ...

## Kohderyhmän tarpeet
- ...

## Innovaatiomahdollisuudet
- ...

## Suositukset hankeideointiin
- ...
```

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
    tools=[google_search],
    output_key="trend_analysis",
)


# Step 2: Idea Generation
idea_generator = LlmAgent(
    model=PLANNER_MODEL,
    name="idea_generator",
    description="Ideoi innovatiivisia hankekonsepteja trendianalyysin pohjalta.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction="""
## SINUN ROOLISI: HANKEIDEOIJA

Lue trendianalyysi: `{trend_analysis}`

### TEHTÄVÄ

Ideoi 3-5 innovatiivista hankekonseptia, jotka:
1. Vastaavat tunnistettuihin tarpeisiin
2. Sopivat rahoittajien prioriteetteihin
3. Hyödyntävät Samhan osaamista
4. Ovat toteutettavissa 2-3 vuodessa

### OUTPUT: Jokaisesta ideasta

```markdown
## Konsepti [N]: [Nimi]

**Ongelma:** Mikä ongelma ratkaistaan?

**Ratkaisu:** Mitä konkreettisesti tehdään?

**Kohderyhmä:** Kenelle?

**Innovatiivisuus:** Mikä on uutta?

**Rahoitusmahdollisuus:** STEA / Erasmus+ / Muu

**Arvio toteutettavuudesta:** 1-5 ⭐

**Riskit:** Mitä voi mennä pieleen?
```

### LOPUKSI

Suosittele parasta konseptia jatkokehitykseen ja perustele valinta.
""",
    output_key="project_ideas",
)


# Step 3: SOTE Validation
sote_validator = LlmAgent(
    model=WORKER_MODEL,
    name="sote_validator",
    description="Arvioi hankeidean sote-näkökulmasta.",
    instruction="""
## SINUN ROOLISI: SOTE-ASIANTUNTIJA (VALIDOINTI)

Lue hankeideat: `{project_ideas}`

### TEHTÄVÄ

Arvioi SUOSITELTU hankeidea SOTE-näkökulmasta:

1. **Mielenterveys**: Miten hanke tukee mielenterveyttä?
2. **Trauma-informoitu**: Onko lähestymistapa trauma-informoitu?
3. **Hyvinvointi**: Miten edistää kokonaisvaltaista hyvinvointia?
4. **Turvallisuus**: Onko kohderyhmälle turvallinen?
5. **Eettisyys**: Onko eettisesti kestävä?

### OUTPUT

```markdown
# SOTE-arviointi: [Hankkeen nimi]

## Vahvuudet
- ...

## Huomioitavaa
- ...

## Suositukset
- ...

## Kokonaisarvio: X/5 ⭐
```
""",
    output_key="sote_validation",
)


# Step 4: Equality Validation
yhdenvertaisuus_validator = LlmAgent(
    model=WORKER_MODEL,
    name="yhdenvertaisuus_validator",
    description="Arvioi hankeidean yhdenvertaisuusnäkökulmasta.",
    instruction="""
## SINUN ROOLISI: YHDENVERTAISUUS-ASIANTUNTIJA (VALIDOINTI)

Lue hankeideat: `{project_ideas}`
Lue SOTE-arviointi: `{sote_validation}`

### TEHTÄVÄ

Arvioi SUOSITELTU hankeidea yhdenvertaisuusnäkökulmasta:

1. **Saavutettavuus**: Onko kaikille saavutettava?
2. **Inkluusio**: Huomioidaanko erilaiset taustat?
3. **Antirasismi**: Edistääkö rakenteellista yhdenvertaisuutta?
4. **Intersektionaalisuus**: Huomioidaanko risteävät identiteetit?
5. **Valtarakenteet**: Puretaanko vai vahvistetaanko?

### OUTPUT

```markdown
# Yhdenvertaisuusarviointi: [Hankkeen nimi]

## Vahvuudet
- ...

## Riskit ja sudenkuopat
- ...

## Suositukset
- ...

## Kokonaisarvio: X/5 ⭐
```
""",
    output_key="yhdenvertaisuus_validation",
)


# Step 5: Methods Planning
methods_planner = LlmAgent(
    model=PLANNER_MODEL,
    name="methods_planner",
    description="Suunnittelee hankkeen menetelmät ja toiminnot.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction="""
## SINUN ROOLISI: KOULUTUSSUUNNITTELIJA (MENETELMÄT)

Lue:
- Hankeideat: `{project_ideas}`
- SOTE-arviointi: `{sote_validation}`
- Yhdenvertaisuusarviointi: `{yhdenvertaisuus_validation}`

### TEHTÄVÄ

Suunnittele hankkeen konkreettiset menetelmät ja toiminnot:

1. **Toimenpiteet**: Mitä tehdään vuosittain?
2. **Menetelmät**: Millaisia osallistavia menetelmiä käytetään?
3. **Materiaalit**: Mitä tuotetaan?
4. **Koulutukset**: Mitä koulutuksia järjestetään?
5. **Aikataulu**: Milloin mitäkin tapahtuu?

### OUTPUT

```markdown
# Menetelmäsuunnitelma: [Hankkeen nimi]

## Vuosi 1: [Teema]
### Toimenpiteet
1. ...

### Menetelmät
- ...

## Vuosi 2: [Teema]
...

## Tuotokset
- ...

## Arviointimenetelmät
- ...
```
""",
    output_key="methods_plan",
)


# Step 6: Proposal Writing
proposal_writer = LlmAgent(
    model=PLANNER_MODEL,
    name="proposal_writer",
    description="Kirjoittaa hakemusluonnoksen.",
    generate_content_config=LONG_OUTPUT_CONFIG,
    instruction="""
## SINUN ROOLISI: KIRJOITTAJA (HAKEMUS)

Lue kaikki aiemmat vaiheet:
- Trendianalyysi: `{trend_analysis}`
- Hankeideat: `{project_ideas}`
- SOTE-arviointi: `{sote_validation}`
- Yhdenvertaisuusarviointi: `{yhdenvertaisuus_validation}`
- Menetelmäsuunnitelma: `{methods_plan}`

### TEHTÄVÄ

Kirjoita TÄYSI STEA-hakemusluonnos:

```markdown
# [Hankkeen nimi]

## 1. Tiivistelmä (max 2000 merkkiä)
...

## 2. Tarve ja tausta
...

## 3. Tavoitteet
### Päätavoite
...
### Osatavoitteet
1. ...

## 4. Kohderyhmä
...

## 5. Toimenpiteet vuosittain
### Vuosi 1
...

## 6. Tulokset ja vaikuttavuus
...

## 7. Seuranta ja arviointi
...

## 8. Yhteistyökumppanit
...

## 9. Aikataulu
...

## 10. Budjetti (arvio)
| Kululaji | Vuosi 1 | Vuosi 2 | Yhteensä |
|----------|---------|---------|----------|
| Henkilöstö | ... | ... | ... |
| ...

## 11. Riskit ja niiden hallinta
...
```
""",
    output_key="proposal_draft",
)


# Step 7: Proposal Review
proposal_reviewer = LlmAgent(
    model=PLANNER_MODEL,
    name="proposal_reviewer",
    description="Arvioi hakemusluonnosta ja antaa palautetta.",
    instruction="""
## SINUN ROOLISI: RAPORTTI-ARVIOIJA (QA)

Lue hakemusluonnos: `{proposal_draft}`

### TEHTÄVÄ

Arvioi hakemusluonnos STEA-kriteerien mukaan:

1. **Tarve ja perustelu** (25%)
2. **Tavoitteet ja mittarit** (20%)
3. **Toimenpiteet ja menetelmät** (25%)
4. **Vaikuttavuus** (15%)
5. **Realistisuus ja budjetti** (15%)

### OUTPUT

```markdown
# Hakemusarviointi

## Kokonaisarvio: X/5 ⭐

## Vahvuudet
1. ...

## Kriittiset kehityskohteet
1. ...

## Konkreettiset parannusehdotukset
1. ...

## Valmis lähettämiseen: ✅ / ❌
```
""",
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
