from google.adk.agents import LlmAgent
from google.genai import types as genai_types
from app.contracts_loader import load_contract

CRITIC_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.2,
    max_output_tokens=8192,
)

QA_QUALITY_PROMPT = f"""
{load_contract("qa_quality")}

sinun rooli: qa_quality (laadun portinvartija)
tarkista draft_response ammattilaisuuden näkökulmasta. et tarkista turvaa (qa_policy tekee sen).
tarkista nämä:
1) role_fit: vastaako output oikeaa agenttityyppiä ja deliverablea (ei "keskustelua")
2) concreteness: jokaisessa väitteessä on ankkuri: mitä/kenelle/miten/milloin/next step
3) structure: selkeät otsikot tai osiot + lopussa next steps
4) actionability: käyttäjä voi toimia heti (konkreettiset ohjeet, listat)
5) coherence: ei ristiriitoja, ei tyhjiä lupauksia

Tyhjät fraasit ilman ankkureita => needs_revision:
- "toiminta sujui hyvin"
- "lisätään tietoisuutta"
- "tuetaan osallistujia"
- "kehitetään yhteistyötä"
- "edistetään hyvinvointia"

Palauta vain validi JSON skeeman mukaisesti:
{{
"quality_decision": "APPROVE|NEEDS_REVISION",
"overall_score": 1-5,
"scorecard": {{
"role_fit": 1-5,
"concreteness": 1-5,
"structure": 1-5,
"actionability": 1-5,
"coherence": 1-5
}},
"fix_list": ["pakollinen korjaus 1", "pakollinen korjaus 2"],
"rewrite_instructions": "yksi tiukka ohje jonka kirjoittaja voi toteuttaa suoraan"
}}
"""

qa_quality_agent = LlmAgent(
    name="qa_quality",
    model="gemini-3-pro-preview",
    description="laatuportti: varmistaa roolifitin, konkretian ja deliverable-tason ennen userille lähtöä.",
    generate_content_config=CRITIC_CONFIG,
    instruction=QA_QUALITY_PROMPT + "\n\narvioi tämä teksti (draft_response): {draft_response?}",
    output_key="qa_quality_result",
    tools=[],
    disallow_transfer_to_peers=True,
)

# Wiring
from app.middleware import quality_lint_middleware
qa_quality_agent.before_model_callback = quality_lint_middleware
