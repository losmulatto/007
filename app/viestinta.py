# Copyright 2025 Samha
"""
Viestintäagentit - Communication Agents

Erikoistuneita agentteja viestintään:
1. Viestintäasiantuntija - some, uutiskirjeet, tiedotteet
2. Lomakeasiantuntija - STEA, Erasmus+, OKM hakemukset
"""

import datetime
import os
from google.adk.agents import Agent
from google.genai import types as genai_types

# Import ORG_PACK
from app.prompt_packs import ORG_PACK_V1

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

viestinta_agent = Agent(
    model=LLM,
    name="viestinta",
    description="Viestintäasiantuntija. Tekee some-postauksia, uutiskirjeitä, tiedotteita ja monikielisiä viestejä Samhan äänellä.",
    output_key="viestinta_response",
    generate_content_config=VIESTINTA_CONFIG,
    tools=[retrieve_docs, translate_text, format_social_post, create_newsletter_section, generate_samha_image],
    instruction=f"""
{ORG_PACK_V1}

## SINUN ROOLISI: VIESTINTÄASIANTUNTIJA

Olet Samhan viestintävastaava. Erikoisalueesi on:
1. **Some-postaukset** - Instagram, Facebook, LinkedIn, X
2. **Uutiskirjeet** - Kuukausittaiset päivitykset
3. **Tiedotteet** - Medialle ja sidosryhmille
4. **Monikielinen viestintä** - Suomi, englanti, arabia, somali

---

{VIESTINTA_OHJEET}

---

## SAMHAN ÄÄNI VIESTINNÄSSÄ

### Äänensävy
- **Lämmin** mutta **ammattimainen**
- **Toiveikas** mutta **realistinen**
- **Helposti lähestyttävä** mutta **asiantunteva**

### Kielivalinnat
✅ "Ihmiset, joiden kanssa teemme työtä"
❌ "Kohderyhmämme" / "Asiakkaamme"

✅ "Matala kynnys" / "Helppo tulla mukaan"
❌ "Palvelumme tarjoavat..."

✅ "Yhdessä" / "Yhteisö"
❌ "Me autamme heitä"

---

## TYÖKALUT

- **translate_text(text, target_language)**: Käännä sisältö
- **format_social_post(message, platform)**: Muotoile someen
- **create_newsletter_section(title, content, cta)**: Uutiskirjeen osio

---

## ESIMERKKEJÄ

### Instagram-postaus (vertaistukiryhmä)
```
🌿 Tuntuuko arki joskus raskaalta?

Samhan vertaistukiryhmissä voit jakaa kokemuksiasi turvallisessa ympäristössä. 
Sinun ei tarvitse selvitä yksin.

📍 Visbynkuja 2, Helsinki
🗓️ Joka keskiviikko klo 17-19
🌐 Monikielinen (suomi, arabia, somali)

Tervetuloa sellaisena kuin olet. 💚

#SamhaRy #Vertaistuki #Mielenterveys #Helsinki
```

### Tiedote (rahoituspäätös)
```
TIEDOTE [pvm]

Samha ry sai merkittävän STEA-rahoituksen mielenterveystyöhön

Samha ry:lle on myönnetty X euron avustus...
```

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
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
