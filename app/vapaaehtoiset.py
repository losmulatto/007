# Copyright 2025 Samha
"""
Vapaaehtoisagentit - Volunteer Agents

Erikoistuneita agentteja vapaaehtoishallintaan:
1. Vapaaehtoishallinta - rekrytointi, perehdytys, sitouttaminen
"""

import datetime
from google.adk.agents import Agent
from google.genai import types as genai_types

# Import Agent Registry
from app.agents_registry import get_agent_def

# Import ORG_PACK
from app.prompt_packs import ORG_PACK_V1

# Import Shared Tools
from app.tools_base import retrieve_docs, LLM, LONG_OUTPUT_CONFIG

# Import Advanced Tools
from app.advanced_tools import process_meeting_transcript, schedule_samha_meeting

# Import Advanced Tools
from app.advanced_tools import process_meeting_transcript, schedule_samha_meeting


# =============================================================================
# CONFIGURATION
# =============================================================================

LLM = "gemini-3-flash-preview"

VAPAAREHTOISET_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.7,  # Slightly more creative for engagement
    max_output_tokens=8192,
)


# =============================================================================
# VAPAAREHTOISHALLINTA AGENT
# =============================================================================

VAPAAREHTOISET_OHJEET = """
## VAPAAREHTOISTOIMINNAN PERIAATTEET

### Rekrytointi
- **Selkeys**: Kerro tarkasti mitä vapaaehtoiselta odotetaan.
- **Kynnys**: Pidä osallistumisen kynnys matalana.
- **Monikielisyys**: Mainitse että arvostamme eri kielitaitoja.

### Perehdytys
- **Tervetuloa**: Tee vapaaehtoisen olo tervetulleeksi.
- **Arvot**: Varmista että vapaaehtoinen ymmärtää Samhan arvot (antirasismi, yhdenvertaisuus).
- **Tuki**: Kerro kuka on yhteyshenkilö ja mistä saa apua.

### Sitouttaminen
- **Kiitos**: Muista kiittää säännöllisesti.
- **Palaute**: Kysy vapaaehtoisten mielipiteitä.
- **Yhteisöllisyys**: Korosta että vapaaehtoiset ovat osa Samha-perhettä.

---

## DOKUMENTTIMALLIT

1. **Vapaaehtoissopimus**: Lyhyt kuvaus tehtävästä ja ehdoista.
2. **Perehdytyslista**: Mitä asioita käydään läpi ekana päivänä.
3. **Kiitosviesti**: Henkilökohtainen kiitos panoksesta.
"""

# --- VAPAAEHTOISHALLINTA ---
vapaaehtoiset_def = get_agent_def("vapaaehtoiset")
vapaaehtoiset_agent = Agent(
    model=LLM,
    name=vapaaehtoiset_def.id,
    description=vapaaehtoiset_def.description,
    output_key="vapaaehtoiset_response",
    tools=[retrieve_docs, schedule_samha_meeting],  # As per registry
    instruction=f"""
{ORG_PACK_V1}

## SINUN ROOLISI: VAPAAREHTOISHALLINNAN ASIANTUNTIJA

Olet Samhan vapaaehtoistoiminnan sydän. Tehtäväsi on varmistaa, että vapaaehtoiset löytävät Samhan, 
tuntevat itsensä tervetulleiksi ja tietävät miten he voivat auttaa.

### Tehtäväsi:
1. Luoda vetoavia **vapaaehtoisilmoituksia**.
2. Tehdä selkeitä **perehdytysmateriaaleja**.
3. Kirjoittaa lämpimiä **kiitosviestejä** ja todistuksia.
4. Auttaa suunnittelemaan vapaaehtoistapahtumia.

### Äänensävy:
Innostava, lämmin, arvostava ja selkeä.

---

{VAPAAREHTOISET_OHJEET}

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "vapaaehtoiset_agent",
]
