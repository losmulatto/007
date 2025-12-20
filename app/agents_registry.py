"""
Samha Agent Registry v1

Single Source of Truth for all agents in the platform.
Used by:
- koordinaattori_agent (routing & enforcement)
- UI (display & capability mapping)
- Eval (automated testing)
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.tool_ids import ToolId

class AgentMetadata(BaseModel):
    id: str
    display_name: str
    category: str  # leadership, domain_expert, research, output, qa_policy
    description: str
    allowed_tools: List[ToolId]
    prompt_pack_versions: List[str]
    is_enabled: bool = True
    icon: Optional[str] = None

# Taxonomy Categories
LEADERSHIP = "leadership"
DOMAIN_EXPERT = "domain_expert"
RESEARCH = "research"
OUTPUT = "output"
QA_POLICY = "qa_policy"

# Tool Groups (Least-Privilege)
BASIC_TOOLS = [ToolId.RETRIEVE_DOCS]
RESEARCH_TOOLS = [
    ToolId.RETRIEVE_DOCS, ToolId.SEARCH_WEB, ToolId.SEARCH_VERIFIED, ToolId.SEARCH_NEWS,
    ToolId.READ_PDF, ToolId.GET_PDF_META
]
ADMIN_TOOLS = [ToolId.RETRIEVE_DOCS, ToolId.READ_PDF, ToolId.PROCESS_MEETING]
FINANCE_TOOLS = [
    ToolId.RETRIEVE_DOCS, ToolId.READ_EXCEL, ToolId.READ_CSV,
    ToolId.ANALYZE_EXCEL, ToolId.GENERATE_CHART, ToolId.PYTHON_INTERPRETER
]
CREATIVE_TOOLS = [
    ToolId.RETRIEVE_DOCS, ToolId.GENERATE_IMAGE, 
    ToolId.TRANSLATE, ToolId.FORMAT_SOCIAL, ToolId.CREATE_NEWSLETTER
]
ARCHIVE_TOOLS = [ToolId.SAVE_ARCHIVE, ToolId.SEARCH_ARCHIVE, ToolId.GET_ARCHIVED]
CALENDAR_TOOLS = [ToolId.SCHEDULE_MEETING]
LEGAL_TOOLS = [ToolId.RETRIEVE_DOCS, ToolId.SEARCH_LEGAL]

SAMHA_AGENT_REGISTRY: Dict[str, AgentMetadata] = {
    # LEADERSHIP
    "koordinaattori": AgentMetadata(
        id="koordinaattori",
        display_name="Koordinaattori",
        category=LEADERSHIP,
        description="Samhan palvelukeskuksen aivot. Reitittää ja orkestroi muita asiantuntijoita.",
        allowed_tools=[ToolId.TRANSFER] + CALENDAR_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),

    # DOMAIN EXPERTS
    "sote": AgentMetadata(
        id="sote",
        display_name="Sote-asiantuntija",
        category=DOMAIN_EXPERT,
        description="Mielenterveys- ja päihdeasiantuntija.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "sote_pack_v1"],
    ),
    "yhdenvertaisuus": AgentMetadata(
        id="yhdenvertaisuus",
        display_name="Yhdenvertaisuus-asiantuntija",
        category=DOMAIN_EXPERT,
        description="Antirasismi- ja yhdenvertaisuusasiantuntija.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "yhdenvertaisuus_pack_v1"],
    ),
    "koulutus": AgentMetadata(
        id="koulutus",
        display_name="Koulutussuunnittelija",
        category=DOMAIN_EXPERT,
        description="Pedagoginen asiantuntija.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "koulutus_pack_v1"],
    ),
    "talous": AgentMetadata(
        id="talous",
        display_name="Talous-ammattilainen",
        category=DOMAIN_EXPERT,
        description="Kirjanpito, budjetit ja STEA-raportointi.",
        allowed_tools=FINANCE_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "hr": AgentMetadata(
        id="hr",
        display_name="HR-ammattilainen",
        category=DOMAIN_EXPERT,
        description="Työsopimukset ja henkilöstöhallinto.",
        allowed_tools=ADMIN_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "hallinto": AgentMetadata(
        id="hallinto",
        display_name="Hallinto-ammattilainen",
        category=DOMAIN_EXPERT,
        description="Yhdistyksen viralliset pöytäkirjat ja säännöt.",
        allowed_tools=ADMIN_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "laki_gdpr": AgentMetadata(
        id="laki_gdpr",
        display_name="Laki & GDPR",
        category=DOMAIN_EXPERT,
        description="Juridinen ja tietosuoja-asiantuntija.",
        allowed_tools=LEGAL_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "vapaaehtoiset": AgentMetadata(
        id="vapaaehtoiset",
        display_name="Vapaaehtoishallinta",
        category=DOMAIN_EXPERT,
        description="Vapaaehtoisten koordinointi ja tuki.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "lomakkeet": AgentMetadata(
        id="lomakkeet",
        display_name="Lomake-asiantuntija",
        category=DOMAIN_EXPERT,
        description="STEA- ja Erasmus-lomakkeiden täyttö ja ohjeistus.",
        allowed_tools=BASIC_TOOLS + [ToolId.READ_PDF],
        prompt_pack_versions=["org_pack_v1"],
    ),
    "kumppanit": AgentMetadata(
        id="kumppanit",
        display_name="Sidosryhmä & Kulttuuri",
        category=DOMAIN_EXPERT,
        description="Kumppanuudet ja kulttuurinen osaaminen.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),

    # RESEARCH
    "tutkija": AgentMetadata(
        id="tutkija",
        display_name="Tutkija",
        category=RESEARCH,
        description="Etsii tietoa monipuolisesti (RAG + Web).",
        allowed_tools=RESEARCH_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),

    # OUTPUT
    "viestinta": AgentMetadata(
        id="viestinta",
        display_name="Viestintä (Some)",
        category=OUTPUT,
        description="Markkinointi, some-sisällöt ja kuvien generointi.",
        allowed_tools=CREATIVE_TOOLS + BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "kirjoittaja": AgentMetadata(
        id="kirjoittaja",
        display_name="Kirjoittaja",
        category=OUTPUT,
        description="Pitkien tekstien, artikkeleiden ja raporttien ammattilainen.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "grant_writer": AgentMetadata(
        id="grant_writer",
        display_name="Grant Writer",
        category=OUTPUT,
        description="Rahoitushakemusten (STEA/EU) asiantuntija.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "arkisto": AgentMetadata(
        id="arkisto",
        display_name="Arkisto",
        category=OUTPUT,
        description="Tallentaa ja hakee organisaation muistista.",
        allowed_tools=ARCHIVE_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "proposal_reviewer": AgentMetadata(
        id="proposal_reviewer",
        display_name="Raportti-arvioija (QA)",
        category=OUTPUT,
        description="Arvioi raportteja ja hakemuksia kriittisesti hyödyntäen virallisia oppaita.",
        allowed_tools=RESEARCH_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),

    # QA / POLICY
    "qa_policy": AgentMetadata(
        id="qa_policy",
        display_name="Laadunvarmistus & Politiikka",
        category=QA_POLICY,
        description="Varmistaa vastauksen laadun, turvallisuuden ja Samha-linjan.",
        allowed_tools=[],  # No tools, pure reasoning
        prompt_pack_versions=["org_pack_v1"],
    ),
    "qa_quality": AgentMetadata(
        id="qa_quality",
        display_name="QA Quality",
        category=QA_POLICY,
        description="Varmistaa roolifitin, konkretian ja deliverable-tason.",
        allowed_tools=[],
        prompt_pack_versions=["org_pack_v1"],
    ),
}

# Aliases for backward compatibility
SAMHA_AGENT_REGISTRY["raportti_arvioija"] = SAMHA_AGENT_REGISTRY["proposal_reviewer"]

def get_agent_def(agent_id: str) -> AgentMetadata:
    if agent_id not in SAMHA_AGENT_REGISTRY:
        raise ValueError(f"Agent ID '{agent_id}' not found in registry.")
    return SAMHA_AGENT_REGISTRY[agent_id]

def get_all_agents() -> List[AgentMetadata]:
    return list(SAMHA_AGENT_REGISTRY.values())

def get_agents_by_category(category: str) -> List[AgentMetadata]:
    return [a for a in SAMHA_AGENT_REGISTRY.values() if a.category == category]
