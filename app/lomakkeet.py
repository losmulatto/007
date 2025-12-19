# Copyright 2025 Samha
"""
Lomakeagentit - Form Agents

Erikoistuneita agentteja lomakkeiden täyttöön:
1. Lomakeasiantuntija - STEA-hakemukset, Erasmus+ raportit, OKM-avustukset
"""

import datetime
import os
from google.adk.agents import Agent
from google.genai import types as genai_types

# Import Agent Registry
from app.agents_registry import get_agent_def

# Import ORG_PACK
from app.prompt_packs import ORG_PACK_V1

# Import Shared Tools
from app.tools_base import retrieve_docs, LLM, LONG_OUTPUT_CONFIG

# Import PDF tools
from app.pdf_tools import read_pdf_content, get_pdf_metadata

# Configuration
LOMAKE_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.3,
    max_output_tokens=16384,
)


# =============================================================================
# LOMAKEASIANTUNTIJA AGENT
# =============================================================================

LOMAKE_OHJEET = """
## LOMAKKEIDEN TÄYTTÖOHJEET

### STEA-hakemus (Avustushakemus)
- **Toiminnan tavoitteet**: Käytä selkeitä, mitattavia tavoitteita.
- **Kohderyhmä**: Määrittele tarkasti (esim. maahanmuuttajanuoret Vantaalla).
- **Tarve**: Perustele tarve tilastoilla tai havainnoilla.
- **Toimenpiteet**: Kuvaile konkreettiset askeleet tavoitteiden saavuttamiseksi.

### Erasmus+ Raportointi
- **Impact (Vaikuttavuus)**: Kuvaile vaikutus osallistujiin ja organisaatioon.
- **Dissemination (Tulosten levittäminen)**: Miten tulokset jaetaan muille.
- **Budget**: Varmista että kulut täsmäävät budjetoituihin summiin.

---

### KRIITTISET SÄÄNNÖT
1. **Faktat ensin**: Älä koskaan keksi tietoja. Jos tieto puuttuu, mainitse se.
2. **Kieli**: Käytä virallista, asiallista suomea (tai englantia Erasmus-hakemuksissa).
3. **Pituus**: Noudata kenttäkohtaisia merkkirajoituksia jos ne on annettu.
"""

# --- LOMAKE-ASIANTUNTIJA ---
lomake_def = get_agent_def("lomakkeet")
lomake_agent = Agent(
    model=LLM,
    name=lomake_def.id,
    description=lomake_def.description,
    output_key="lomake_response",
    tools=[retrieve_docs, read_pdf_content],  # As per registry
    instruction=f"""
{ORG_PACK_V1}

## SINUN ROOLISI: LOMAKEASIANTUNTIJA

Olet Samhan asiantuntija virallisten hakemusten ja raporttien täyttämisessä. 
Tehtäväsi on auttaa täyttämään lomakkeiden kentät tarkasti ja vakuuttavasti.

---

{LOMAKE_OHJEET}

---

## TYÖSKENTELYTAPA

1. **Analyysi**: Lue lomakkeen kysymys huolellisesti.
2. **Tiedonhaku**: Käytä `retrieve_docs`-työkalua hakeaksesi ohjeita (RAG) tai aikaisempia dokumentteja.
3. **Luonnostelu**: Tee ehdotus tekstiksi.
4. **Viimeistely**: Tarkista että teksti vastaa kysymykseen ja noudattaa virallista kieltä.

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "lomake_agent",
    "retrieve_docs",
]
