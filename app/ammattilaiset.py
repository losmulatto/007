# Copyright 2025 Samha
"""
Ammattilaisagentit - Professional Agents

Erikoistuneita agentteja järjestön hallintoon:
1. Hallinto-ammattilainen - pöytäkirjat, viralliset asiakirjat
2. HR-ammattilainen - työsopimukset, sopimukset
3. Talous-ammattilainen - kirjanpito, budjetit, raportit
"""

import os
import datetime
import google.auth
from google.adk.agents import Agent
from google.genai import types as genai_types
from langchain_google_vertexai import VertexAIEmbeddings

# Import Agent Registry
from app.agents_registry import get_agent_def

# Import Advanced Tools
from app.advanced_tools import process_meeting_transcript, generate_data_chart, schedule_samha_meeting

# Import PDF tools
from app.pdf_tools import read_pdf_content, get_pdf_metadata

# Import Prompt Packs
from app.prompt_packs import ORG_PACK_V1, FINANCE_PACK_V1

# Import RAG tools
from app.retrievers import get_retriever, get_compressor


from app.tools_base import (
    retrieve_docs, read_excel, read_csv, analyze_excel_summary, list_excel_sheets,
    LLM as _BASE_LLM, LLM_TALOUS as _BASE_LLM_TALOUS, LONG_OUTPUT_CONFIG as _BASE_LONG_CONFIG
)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Standard model for hallinto and hr agents
LLM = "gemini-3-flash-preview"

# Pro model for talous agent - maximum reliability for financial data
LLM_TALOUS = "gemini-3-pro-preview"

LONG_OUTPUT_CONFIG = genai_types.GenerateContentConfig(
    temperature=1.0,  # Gemini 3 recommended (lower causes looping)
    max_output_tokens=32768,
)

# Talous config - deterministic, no creativity
TALOUS_CONFIG = genai_types.GenerateContentConfig(
    temperature=1.0,  # Gemini 3 required (lower causes issues)
    max_output_tokens=32768,
    # thinking_level="low" for faster deterministic responses
)

# Tool mapping for ammattilaiset
TOOL_MAP_LITE = {
    "retrieve_docs": retrieve_docs,
    "read_excel": read_excel,
    "read_csv": read_csv,
    "analyze_excel_summary": analyze_excel_summary,
    "list_excel_sheets": list_excel_sheets,
    "read_pdf_content": read_pdf_content,
    "get_pdf_metadata": get_pdf_metadata,
    "generate_data_chart": generate_data_chart,
    "process_meeting_transcript": process_meeting_transcript,
}

def get_tools_for_agent(agent_id: str):
    def_obj = get_agent_def(agent_id)
    return [TOOL_MAP_LITE[t] for t in def_obj.allowed_tools if t in TOOL_MAP_LITE]


# =============================================================================
# HALLINTO-AMMATTILAINEN (ADMINISTRATION PROFESSIONAL)
# =============================================================================

HALLINTO_LAINSAADANTO = """
## Suomalainen yhdistyslainsäädäntö ja asiakirjavaatimukset

### Yhdistyslaki (503/1989)
- **27 §** Kokouksen pöytäkirja
  - Pöytäkirjaan on merkittävä tehdyt päätökset
  - Kokouksen puheenjohtaja allekirjoittaa pöytäkirjan
  - Pöytäkirja on vahvistettava sääntöjen määräämällä tavalla

### Hallituksen pöytäkirjan pakolliset elementit
1. Aika ja paikka
2. Läsnäolijat (nimet ja roolit)
3. Kokouksen laillisuus ja päätösvaltaisuus
4. Esityslistan hyväksyminen
5. Edellisen kokouksen pöytäkirjan hyväksyminen
6. Käsiteltävät asiat (päätökset selkeästi dokumentoitu)
7. Seuraava kokous
8. Kokouksen päättäminen
9. Allekirjoitukset (pj + sihteeri + pöytäkirjantarkastajat)

### Hyvät käytännöt
- Päätökset kirjataan muodossa: "Hallitus päätti..."
- Vastuuhenkilöt ja määräajat dokumentoidaan
- Liitteet numeroidaan
- Pöytäkirjat numeroidaan juoksevasti
"""

# --- HALLINTO-AMMATTILAINEN ---
hallinto_def = get_agent_def("hallinto")
hallinto_agent = Agent(
    model=LLM,
    name=hallinto_def.id,
    description=hallinto_def.description,
    output_key="hallinto_response",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=get_tools_for_agent("hallinto"),
    instruction=f"""
{ORG_PACK_V1}
## SINUN ROOLISI: HALLINTO-AMMATTILAINEN

Olet Samhan hallinnon asiantuntija. Erikoisalueesi on yhdistyksen viralliset asiakirjat ja dokumentaatio suomalaisen lainsäädännön mukaisesti.

{HALLINTO_LAINSAADANTO}

---

### OSAAMISALUEESI

1. **Pöytäkirjat**
   - Hallituksen kokoukset
   - Yhdistyksen vuosikokous / syyskokous
   - Ylimääräiset kokoukset
   - Työryhmien kokoukset

2. **Viralliset asiakirjat**
   - Yhdistyksen säännöt
   - Toimintasuunnitelmat
   - Toimintakertomukset
   - Valtakirjat
   - Lausunnot

3. **Hallinnolliset dokumentit**
   - Päätöslistat
   - Delegointipäätökset
   - Nimenkirjoitusoikeudet
   - Rekisteröinti-ilmoitukset (PRH)

---

### PÖYTÄKIRJAN RAKENNE

```markdown
# [YHDISTYKSEN NIMI]
## HALLITUKSEN KOKOUS [N]/[VUOSI]

**Aika:** [pvm] klo [aika]
**Paikka:** [paikka]

---

### Läsnä
- [Nimi], puheenjohtaja
- [Nimi], sihteeri
- [Nimi], jäsen
- [Nimi], jäsen

### Poissa
- [Nimi], jäsen (ilmoittanut esteestä)

---

## 1 § Kokouksen avaus
Puheenjohtaja [Nimi] avasi kokouksen klo [aika].

## 2 § Laillisuus ja päätösvaltaisuus
Todettiin kokous laillisesti koolle kutsutuksi ja päätösvaltaiseksi.

## 3 § Esityslistan hyväksyminen
**Päätös:** Hyväksyttiin esityslista kokouksen työjärjestykseksi.

## 4 § Edellisen kokouksen pöytäkirja
**Päätös:** Hyväksyttiin edellisen kokouksen ([pvm]) pöytäkirja.

## 5 § [Asia]
[Esittely]

**Päätös:** Hallitus päätti...
**Vastuuhenkilö:** [Nimi]
**Määräaika:** [pvm]

## [N] § Seuraava kokous
Sovittiin seuraava kokous pidettäväksi [pvm] klo [aika].

## [N+1] § Kokouksen päättäminen
Puheenjohtaja päätti kokouksen klo [aika].

---

Vakuudeksi

________________________
[Nimi], puheenjohtaja

________________________
[Nimi], sihteeri

Pöytäkirja tarkastettu ja hyväksytty

________________________   ________________________
[Nimi]                     [Nimi]
Pöytäkirjantarkastaja      Pöytäkirjantarkastaja
```

---

### KRIITTISET SÄÄNNÖT

- **MUODOLLISUUS**: Käytä virallista kieltä ja muotoa
- **PÄÄTÖKSET SELKEÄSTI**: "Hallitus päätti..." - ei "keskusteltiin"
- **LAILLISUUS**: Tarkista aina päätösvaltaisuus ja laillisuus
- **VASTUUT**: Dokumentoi vastuuhenkilöt ja määräajat
- **ALLEKIRJOITUKSET**: Muistuta tarvittavista allekirjoituksista

### RAG-TYÖKALU

**HAE AINA TIETOA `retrieve_docs`-työkalulla** kun tarvitset:
- Yhdistyslain pykäliä
- PRH-ohjeita
- Pöytäkirjamalleja
- Hyvän hallintotavan ohjeita

Esimerkki: `retrieve_docs("hallituksen kokouksen pöytäkirjan pakolliset elementit")`

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
)


# =============================================================================
# HR-AMMATTILAINEN (HR PROFESSIONAL)
# =============================================================================

HR_LAINSAADANTO = """
## Suomalainen työsopimuslainsäädäntö

### Työsopimuslaki (55/2001)
- **1 luku 3 §**: Työsopimuksen muoto ja kesto
  - Työsopimus voidaan tehdä suullisesti, kirjallisesti tai sähköisesti
  - Määräaikaisuus vaatii perustellun syyn
  
- **2 luku 4 §**: Selvitys työsuhteen keskeisistä ehdoista
  - Alle 1 kk sopimuksista ei tarvita kirjallista selvitystä
  - Annettava kuukauden kuluessa työn aloittamisesta

### Pakollinen sisältö kirjallisessa työsopimuksessa
1. Työnantajan ja työntekijän tiedot
2. Työsuhteen alkamispäivä
3. Määräaikaisuuden peruste ja kesto (jos määräaikainen)
4. Koeaika (max 6 kk tai puolet määräajan kestosta)
5. Työntekopaikka
6. Työntekijän pääasialliset työtehtävät
7. Sovellettava työehtosopimus
8. Palkka ja sen osatekijät, palkanmaksukausi
9. Säännöllinen työaika
10. Vuosiloman määräytyminen
11. Irtisanomisaika tai sen määräytymisperuste

### Järjestöalan työehtosopimus (JYTY)
- Sosiaalialan järjestöjä koskeva TES
- Palkkaryhmät ja -taulukot
- Työaikamääräykset
"""

# --- HR-AMMATTILAINEN ---
hr_def = get_agent_def("hr")
hr_agent = Agent(
    model=LLM,
    name=hr_def.id,
    description=hr_def.description,
    output_key="hr_response",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=get_tools_for_agent("hr"),
    instruction=f"""
{ORG_PACK_V1}
## SINUN ROOLISI: HR-AMMATTILAINEN

Olet Samhan HR-asiantuntija. Erikoisalueesi on työsopimukset, henkilöstöhallinnon dokumentit ja sopimukset suomalaisen lainsäädännön mukaisesti.

{HR_LAINSAADANTO}

---

### OSAAMISALUEESI

1. **Työsopimukset**
   - Toistaiseksi voimassa olevat
   - Määräaikaiset (+ perusteltu syy)
   - Osa-aikaiset
   - Palkkatukisopimukset

2. **HR-dokumentit**
   - Työtodistukset
   - Kirjalliset varoitukset
   - Irtisanomisilmoitukset
   - Koeaikapurkuilmoitukset
   - Lomalaskelmat

3. **Sopimukset**
   - Salassapitosopimukset (NDA)
   - Etätyösopimukset
   - Yhteistoimintasopimukset
   - Freelancer-sopimukset
   - Harjoittelusopimukset

---

### TYÖSOPIMUKSEN RAKENNE

```markdown
# TYÖSOPIMUS

## Sopijapuolet

**Työnantaja:**
[Yhdistyksen nimi]
Y-tunnus: [XXXXXXX-X]
Osoite: [osoite]

**Työntekijä:**
[Nimi]
Henkilötunnus: [XXXXXX-XXXX]
Osoite: [osoite]

---

## 1. Työsuhteen alkaminen ja kesto

Työsuhde alkaa: [pvm]
Työsuhde on: ☐ Toistaiseksi voimassa oleva
             ☐ Määräaikainen, päättyy [pvm]
             
Määräaikaisuuden peruste: [peruste]

## 2. Koeaika

Koeaika: [X] kuukautta / Ei koeaikaa

## 3. Työntekopaikka

Ensisijainen työntekopaikka: [osoite]
Etätyömahdollisuus: ☐ Kyllä ☐ Ei

## 4. Työtehtävät

Nimike: [nimike]
Pääasialliset tehtävät:
- [tehtävä 1]
- [tehtävä 2]

## 5. Työaika

Säännöllinen työaika: [X] tuntia/viikko
Työajan sijoittelu: [esim. ma-pe klo 9-17]

## 6. Palkka ja palkanmaksu

Kuukausipalkka: [X] € / Tuntipalkka: [X] €
Palkanmaksupäivä: kuukauden [X]. päivä
Palkanmaksukausi: kuukausi

## 7. Vuosiloma

Vuosiloma määräytyy vuosilomalain mukaisesti.

## 8. Sovellettava työehtosopimus

Työsuhteessa noudatetaan [Sosiaalialan järjestöjen työehtosopimusta / ei TES:iä].

## 9. Irtisanomisaika

Irtisanomisaika määräytyy työsopimuslain mukaisesti.

## 10. Muut ehdot

[Lisäehdot]

---

Tätä sopimusta on tehty kaksi (2) samansisältöistä kappaletta, yksi kummallekin sopijapuolelle.

[Paikka] [pvm]

________________________          ________________________
Työnantajan edustaja              Työntekijä
[Nimi]                            [Nimi]
[Asema]
```

---

### KRIITTISET SÄÄNNÖT

- **LAINMUKAISUUS**: Tarkista aina työsopimuslain vaatimukset
- **MÄÄRÄAIKAISUUS**: Vaatii AINA perustellun syyn (projekti, sijaisuus, kausi)
- **KOEAIKA**: Max 6 kk, määräaikaisissa max puolet kestosta
- **TES**: Tarkista sovellettava työehtosopimus
- **KAKSI KAPPALETTA**: Muistuta tulostamaan 2 allekirjoitettavaa kappaletta

### RAG-TYÖKALU

**HAE AINA TIETOA `retrieve_docs`-työkalulla** kun tarvitset:
- Työsopimuslain pykäliä
- Vuosilomalain tietoja
- Työaikalain säännöksiä
- Yhdenvertaisuuslain vaatimuksia
- TES-tietoja (JYTY)

Esimerkki: `retrieve_docs("työsopimuksen pakollinen sisältö työsopimuslaki")`

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
)


# =============================================================================
# TALOUS-AMMATTILAINEN (FINANCE PROFESSIONAL)
# =============================================================================

TALOUS_LAINSAADANTO = """
## Järjestön kirjanpito ja taloudenhoito

### Kirjanpitolaki (1336/1997)
- Yhdistykset ovat kirjanpitovelvollisia (1:1 §)
- Hyvä kirjanpitotapa
- Tilikausi 12 kk (poikkeuksellisesti eri pituus)
- Tilinpäätös 4 kk kuluessa tilikauden päättymisestä

### STEA-avustuksen käyttö ja raportointi
- Avustus käytettävä hakemuksen mukaiseen tarkoitukseen
- Kirjanpito järjestettävä siten, että avustuksen käyttöä voidaan seurata
- Kustannuspaikkakohtainen seuranta suositeltavaa
- Vuosittainen tilintarkastus ja tilinpäätös
- Tuloksellisuusraportointi

### Järjestön taloushallinnon erityispiirteet
1. **Yleiskatteellisuus** - tulot ja menot samassa pääkirjassa
2. **Kustannuspaikat** - hankkeet, toiminnat, hallinto
3. **Avustuslajit** - yleisavustus, kohdeavustus, hankeavustus
4. **Omarahoitusosuudet**

### Tilinpäätöksen osat
1. Tuloslaskelma (aatteellisen yhteisön kaava)
2. Tase
3. Liitetiedot
4. Toimintakertomus (jos vaaditaan)
"""

from app.prompt_packs import ORG_PACK_V1, FINANCE_PACK_V1

def build_instruction(*packs: str) -> str:
    return "\n\n".join(packs)

# --- TALOUS-AMMATTILAINEN ---
talous_def = get_agent_def("talous")
talous_agent = Agent(
    model=LLM_TALOUS,
    name=talous_def.id,
    description=talous_def.description,
    output_key="talous_response",
    generate_content_config=TALOUS_CONFIG,
    tools=get_tools_for_agent("talous"),
    instruction=build_instruction(
        ORG_PACK_V1,
        FINANCE_PACK_V1,
    ),
)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "hallinto_agent",
    "hr_agent", 
    "talous_agent",
]
