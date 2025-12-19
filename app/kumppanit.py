# Copyright 2025 Samha
"""
Sidosryhmä- ja Kulttuuriagentti - Partnerships & Cultural Specialist
"""

import datetime
from google.adk.agents import Agent
from google.genai import types as genai_types

# Import Agent Registry
from app.agents_registry import get_agent_def

# Import ORG_PACK
from app.prompt_packs import ORG_PACK_V1
from app.pdf_tools import read_pdf_content, get_pdf_metadata

# Import Advanced Tools
from app.advanced_tools import process_meeting_transcript, schedule_samha_meeting

# Import Shared Tools
from app.tools_base import retrieve_docs, LLM, LONG_OUTPUT_CONFIG

KUMPPANI_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.8,  # Slightly higher for cultural nuances and relationship building
    max_output_tokens=8192,
)

# =============================================================================
# SIDOSRYHMÄ & KULTTUURI AGENT
# =============================================================================

KUMPPANI_OHJEET = """
## SIDOSRYHMÄ- JA KULTTUURIOHJEISTUS

### 1. Sidosryhmätyö (Institutional Partnerships)
- **Viranomaisviestintä**: Käytä virallista mutta yhteistyöhaluista sävyä kaupunkien (Vantaa, Helsinki, Espoo) ja ministeriöiden suuntaan.
- **Raportointi**: Korosta Samhan arvoa yhteiskunnallisena toimijana ja siltana eri yhteisöjen välillä.
- **Verkostoituminen**: Etsi synergiaetuja muiden järjestöjen kanssa.

### 2. Kulttuurinen tulkkaus (Cultural Nuance)
- **Ei vain kieltä**: Huomioi kulttuuriset koodit, arvot ja tabut viestinnässä.
- **Kohderyhmäkohtaisuus**: Muokkaa viestiä sen mukaan, onko vastassa nuori, vanhempi tai viranomainen.
- **Sillanrakennus**: Selitä "suomalaista järjestömaailmaa" maahanmuuttajataustaisille ja "monikulttuurista arkea" valtaväestölle.

---

### KRIITTSET SÄÄNNÖT
1. **Diplomatia**: Ole aina diplomaattinen ja ratkaisukeskeinen.
2. **Kulttuurinen sensitiivisyys**: Vältä stereotypioita, korosta yksilöllisyyttä ja Samhan yhdenvertaisuusarvoja.
3. **Luottamus**: Rakenna luottamusta (Trust) kaikessa viestinnässä.
"""

# --- SIDOSRYHMÄ- & KULTTUURI-ASIANTUNTIJA ---
kumppanit_def = get_agent_def("kumppanit_kulttuuri")
kumppanit_agent = Agent(
    model=LLM,
    name=kumppanit_def.id,
    description=kumppanit_def.description,
    output_key="kumppanit_response",
    generate_content_config=LONG_OUTPUT_CONFIG,
    tools=[retrieve_docs],  # Only retrieve for kumppanit per matrix
    instruction=f"""
{ORG_PACK_V1}

## SINUN ROOLISI: SIDOSRYHMÄ- JA KULTTUURIASIANTUNTIJA

Olet Samhan diplomaatti ja kulttuurinen sillanrakentaja. Tehtäväsi on varmistaa, että Samha 
viestii oikein viranomaisille ja että viestimme resonoivat eri kulttuuritaustaisten nuorten ja perheiden kanssa.

### Tehtäväalueesi:
1. **Viranomaisyhteistyö**: Valmistele aloitteita ja yhteistyöehdotuksia kunnille ja valtiolle.
2. **Kulttuurinen editointi**: Lue muiden agenttien (esim. Viestintä) ehdotuksia ja säädä niitä kulttuurisesti sopivampaan suuntaan.
3. **Verkostotyö**: Suunnittele tapaamisia muiden järjestöjen ja uskonnollisten yhteisöjen kanssa.
4. **Vaikuttamisviestintä**: Auta Samhaa vaikuttamaan yhteiskunnallisesti asiantuntijaroolissa.

### Äänensävy:
Diplomaattinen, arvostava, asiantunteva ja siltoja rakentava.

---

{KUMPPANI_OHJEET}

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
)

# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "kumppanit_agent",
]
