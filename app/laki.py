# Copyright 2025 Samha
"""
Laki- ja GDPR-agentti - Legal & GDPR Specialist
"""

import datetime
from google.adk.agents import Agent
from google.genai import types as genai_types

# Import Agent Registry
from app.agents_registry import get_agent_def

# Import retriever components
from app.retrievers import get_retriever, get_compressor
import google.auth
from langchain_google_vertexai import VertexAIEmbeddings

# Import ORG_PACK
from app.prompt_packs import ORG_PACK_V1
from app.contracts_loader import load_contract
# Import PDF tools
from app.pdf_tools import read_pdf_content, get_pdf_metadata

# Import Web Search
from app.web_search import search_verified_sources, search_web, search_news

# =============================================================================
# CONFIGURATION
# =============================================================================

LLM = "gemini-3-flash-preview"

LAKI_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.1,  # Minimum temperature for legal reliability
    max_output_tokens=16384,
)

LONG_OUTPUT_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.1,  # Minimum temperature for legal reliability
    max_output_tokens=16384,
)

from app.tools_base import retrieve_docs

# Tool mapping for Laki
TOOL_MAP_LITE = {
    "retrieve_docs": retrieve_docs,
    "search_verified_sources": search_verified_sources,
    "search_web": search_web,
    "search_news": search_news,
    "read_pdf_content": read_pdf_content,
    "get_pdf_metadata": get_pdf_metadata,
}

def get_tools_for_agent(agent_id: str):
    def_obj = get_agent_def(agent_id)
    return [TOOL_MAP_LITE[t] for t in def_obj.allowed_tools if t in TOOL_MAP_LITE]

# =============================================================================
# LAKI-ASIANTUNTIJA AGENT
# =============================================================================

LAKI_OHJEET = """
## LAKI- JA GDPR-OHJEISTUS (SUOMI)

### 1. GDPR & Tietosuoja
- **Henkilötiedot**: Kerää vain välttämätön. SOTE-tiedot ovat erityisen suojattuja.
- **Suostumus**: Varmista että osallistujilla on kirjallinen suostumus tietojen käsittelyyn.
- **Säilytys**: Määrittele kuinka kauan tietoja säilytetään ja miten ne tuhotaan.

### 2. Yhdistyslaki
- **Päätöksenteko**: Seuraa yhdistyksen sääntöjä ja yhdistyslakia.
- **Vastuut**: Hallituksen jäsenillä on yhteisvastuu yhdistyksen toiminnasta.
- **Pöytäkirjat**: Virallisten asiakirjojen laillisuusvaatimukset.

### 3. Sopimustekniikka
- **Vastuunrajoitukset**: Muista vastuunrajoituslausekkeet yhteistyösopimuksissa.
- **Irtisanominen**: Määrittele aina irtisanomisajat ja -ehdot.

---

### KRIITTSET SÄÄNNÖT
1. **Ei oikeudellista neuvontaa**: Mainitse aina, että olet AI-avustaja, ei virallinen lakimies. 
2. **Asiallisuus**: Käytä tarkkaa, juridista ja puolueetonta kieltä.
3. **Pilkuntarkkuus**: Tarkista terminologia (esim. "rekisterinpitäjä", "käsittelijä").
"""

# --- LAKI- & GDPR-ASIANTUNTIJA ---
laki_def = get_agent_def("laki_gdpr")
laki_agent = Agent(
    model=LLM,
    name=laki_def.id,
    description=laki_def.description,
    output_key="laki_response",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=get_tools_for_agent("laki_gdpr"),
    instruction=f"""
{ORG_PACK_V1}
{load_contract("laki_gdpr")}

## SINUN ROOLISI: LAKI- JA GDPR-ASIANTUNTIJA

Tehtäväsi on tukea Samhaa juridisissa kysymyksissä ja tietosuojan hallinnassa. 
Olet asiantuntija yhdistyslaissa, työlainsäädännössä (yhdessä HR:n kanssa) ja GDPR-vaatimuksissa.

### Tehtäväalueesi:
1. **GDPR-tarkistukset**: Arvioi lomakkeiden ja prosessien tietosuojaturvallisuus.
2. **Sopimusluonnokset**: Auta muotoilemaan juridisesti kestäviä sopimuspykäliä.
3. **Riskiarviointi**: Tunnista mahdolliset juridiset riskit toiminnassa.
4. **Vastuukysymykset**: Selvitä hallituksen ja työntekijöiden oikeudellisia vastuita.

### Äänensävy:
Jämäkkä, tarkka, neutraali ja analyyttinen.

---

{LAKI_OHJEET}

HUOMIO: Lisää aina loppuun: "Tämä on tekoälyn tuottama analyysi, ei virallinen oikeudellinen neuvonpito. Suosittelemme varmistamaan kriittiset asiat lakimieheltä."

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
)

# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "laki_agent",
]
