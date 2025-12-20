# Copyright 2025 Samha
"""
Viestintäagentit - Communication Agents

Erikoistuneita agentteja viestintään:
1. Viestintäasiantuntija - some, uutiskirjeet, tiedotteet
2. Lomakeasiantuntija - STEA, Erasmus+, OKM hakemukset
"""

import datetime
import os
from google.adk.agents import Agent, SequentialAgent
from google.genai import types as genai_types

# Import ORG_PACK
from app.prompt_packs import ORG_PACK_V1
from app.contracts_loader import load_contract

# Import Shared Tools
from app.tools_base import retrieve_docs, LLM, LONG_OUTPUT_CONFIG

# Import ImageGen tool
from app.image_tools import generate_samha_image

# Configuration
VIESTINTA_CONFIG = genai_types.GenerateContentConfig(
    temperature=1.0,
    max_output_tokens=8192,
)


# =============================================================================
# TOOLS: TRANSLATION
# =============================================================================

def translate_text(
    text: str,
    target_language: str,
    source_language: str = "auto"
) -> str:
    """
    Kääntää tekstin kohdekielelle. Tukee Samhan käyttämiä kieliä.
    
    Args:
        text: Käännettävä teksti.
        target_language: Kohdekieli: 'fi', 'en', 'ar', 'so', 'ru', 'fa' (dari).
        source_language: Lähdekieli (auto = tunnista automaattisesti).
    
    Returns:
        str: Käännetty teksti.
    """
    language_names = {
        'fi': 'suomi',
        'en': 'englanti', 
        'ar': 'arabia',
        'so': 'somali',
        'ru': 'venäjä',
        'fa': 'dari/farsi'
    }
    
    target_name = language_names.get(target_language, target_language)
    
    # This is a placeholder - actual translation would use Vertex AI Translate API
    # For now, return instruction for the LLM to translate in its response
    return f"""## Käännöspyyntö

**Käännä seuraava teksti kielelle: {target_name} ({target_language})**

---
{text}
---

Huomioi Samhan viestintäohjeet käännöksessä:
- Kulttuurisensitiivinen kieli
- Selkeä ja ymmärrettävä
- Säilytä alkuperäinen merkitys
"""


def format_social_post(
    message: str,
    platform: str,
    include_hashtags: bool = True
) -> str:
    """
    Muotoilee somen julkaisun oikeaan muotoon.
    
    Args:
        message: Julkaisun sisältö.
        platform: 'instagram', 'facebook', 'linkedin', 'twitter'.
        include_hashtags: Lisää hashtagit.
    
    Returns:
        str: Muotoiltu julkaisu.
    """
    limits = {
        'instagram': 2200,
        'facebook': 63206,
        'linkedin': 3000,
        'twitter': 280
    }
    
    limit = limits.get(platform.lower(), 2200)
    
    hashtags = ""
    if include_hashtags:
        hashtags = """

---
**Suositellut hashtagit:**
#SamhaRy #Mielenterveys #Hyvinvointi #Maahanmuuttajat #Helsinki #Vertaistuki #MatalaKynnys"""
    
    return f"""## {platform.capitalize()} -julkaisu

**Merkkirajoitus:** {limit} merkkiä
**Nykyinen pituus:** {len(message)} merkkiä
**Status:** {'✅ OK' if len(message) <= limit else '⚠️ Liian pitkä!'}

---
{message}
{hashtags}
"""


def create_newsletter_section(
    title: str,
    content: str,
    call_to_action: str = ""
) -> str:
    """
    Luo uutiskirjeen osion HTML-muodossa.
    
    Args:
        title: Osion otsikko.
        content: Sisältö.
        call_to_action: CTA-teksti (esim. "Lue lisää").
    
    Returns:
        str: HTML-muotoiltu osio.
    """
    cta_html = ""
    if call_to_action:
        cta_html = f'''
<p style="text-align: center; margin-top: 20px;">
    <a href="#" style="background-color: #2E7D32; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">
        {call_to_action}
    </a>
</p>'''
    
    return f"""
<!-- Newsletter Section -->
<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 30px;">
    <tr>
        <td style="padding: 20px; background-color: #f5f5f5; border-radius: 8px;">
            <h2 style="color: #1B5E20; margin: 0 0 15px 0; font-family: Arial, sans-serif;">
                {title}
            </h2>
            <p style="color: #333; line-height: 1.6; font-family: Arial, sans-serif;">
                {content}
            </p>
            {cta_html}
        </td>
    </tr>
</table>
"""


# =============================================================================
# VIESTINTÄASIANTUNTIJA AGENT
# =============================================================================

VIESTINTA_OHJEET = """
## SOME-POSTAUSTEN PARHAAT KÄYTÄNNÖT

### Instagram
- Visuaalinen sisältö etusijalla
- 3-5 relevanttia hashtagia
- Tarina (kuva + teksti)
- Emojit maltillisesti

### Facebook
- Pidempi teksti OK
- Linkit toimivat hyvin
- Tapahtumat ja ryhmät
- Yhteisön osallistaminen

### LinkedIn
- Ammattimaisempi sävy
- Artikkelit ja asiantuntijuus
- Verkostoituminen
- Ei liikaa emojeja

### X (Twitter)
- Lyhyt ja ytimekäs (280 merkkiä)
- Ajankohtaiset aiheet
- Keskusteluun osallistuminen

---

## UUTISKIRJEEN RAKENNE

1. **Tervehdys** - Lyhyt ja lämmin
2. **Pääuutinen** - Tärkein asia ensin
3. **Tulevat tapahtumat** - Listat toimivat
4. **Spotissa** - Nostoja (vapaaehtoinen, asiakas)
5. **CTA** - Mitä haluamme lukijan tekevän
6. **Allekirjoitus** - Tariq Omar, Samha ry

---

## TIEDOTTEEN RAKENNE

1. **Otsikko** - Kertoo uutisen ytimen
2. **Ingressi** - Kuka, mitä, milloin, missä (1-2 lausetta)
3. **Leipäteksti** - Tarkemmat tiedot
4. **Sitaatti** - Toiminnanjohtajan tai asiantuntijan kommentti
5. **Taustatiedot** - Lyhyt kuvaus Samhasta
6. **Yhteystiedot** - Lisätiedot medialle
"""

viestinta_draft_agent = Agent(
    model=LLM,
    name="viestinta_draft",
    description="Drafts communication materials.",
    output_key="viestinta_draft",
    generate_content_config=VIESTINTA_CONFIG,
    tools=[retrieve_docs, translate_text, format_social_post, create_newsletter_section, generate_samha_image],
    instruction=f"""
{ORG_PACK_V1}
{load_contract("viestinta")}
{VIESTINTA_OHJEET}

## SINUN ROOLISI: VIESTINTÄASIANTUNTIJA (DRAFT)
Tuota ENSIMMÄINEN VERSIO viestistä.
Muista Samhan äänensävy.
""",
)

viestinta_refiner_agent = Agent(
    model=LLM,
    name="viestinta_refiner",
    description="Refines communication materials.",
    output_key="viestinta_response",
    instruction="""
Olet kokenut viestintäpäällikkö.
Lue edellinen viesti (viestinta_draft).
Korjaa ja paranna:
1. Varmista "Ihmiset ensin" -kieli (ei "kohderyhmä", vaan "ihmiset").
2. Poista kapulakieli ("jalkauttaminen") -> "tekeminen".
3. PAKOTOLLINEN: Lisää Call-to-Action (CTA). Esim: "Lue lisää", "Ota yhteyttä", "Tule mukaan".
4. Tarkista emojien määrä (maltillisuus).

Palauta vain valmis, hiottu teksti.
""",
)

def _ensure_cta(text: str) -> str:
    if not text:
        return text
    cta_keywords = ["ota yhteyttä", "lue lisää", "tule mukaan", "ilmoittaudu", "tutustu", "kysy lisää", "liity"]
    lowered = text.lower()
    if any(k in lowered for k in cta_keywords):
        return text
    return text.rstrip() + "\n\nOta yhteyttä tai tule mukaan — kerromme mielellämme lisää."

async def viestinta_cta_callback(context=None, **kwargs):
    ctx = context or kwargs.get("callback_context")
    if not ctx:
        return
    session = getattr(ctx, "session", None)
    if not session or not hasattr(session, "state"):
        return
    state = session.state
    response = state.get("viestinta_response", "")
    state["viestinta_response"] = _ensure_cta(response)

viestinta_refiner_agent.after_model_callback = viestinta_cta_callback

viestinta_agent = SequentialAgent(
    name="viestinta",
    description="Viestintäasiantuntija. Tekee some-postauksia, uutiskirjeitä, tiedotteita ja monikielisiä viestejä Samhan äänellä.",
    sub_agents=[viestinta_draft_agent, viestinta_refiner_agent]
)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "viestinta_agent",
    "translate_text",
    "format_social_post",
    "create_newsletter_section",
]
