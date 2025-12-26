"""
Samha Agent Registry v1

Single Source of Truth for all agents in the platform.
Used by:
- koordinaattori_agent (routing & enforcement)
- UI (display & capability mapping)
- Eval (automated testing)
"""

from typing import List, Dict, Any, Optional, Union
from enum import Enum
from dataclasses import dataclass, field
from app.tool_ids import ToolId

@dataclass
class AgentMetadata:
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
    "samha_context_checker": AgentMetadata(
        id="samha_context_checker",
        display_name="Konteksti-tarkistaja",
        category=LEADERSHIP,
        description="Varmistaa pyynnön Samha-yhteensopivuuden (STEA, EU).",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "trend_planner": AgentMetadata(
        id="trend_planner",
        display_name="Trendi-suunnittelija",
        category=LEADERSHIP,
        description="Analysoi trendejä ja suunnittelee tutkimusvaiheen.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),

    # DOMAIN EXPERTS
    "sote": AgentMetadata(
        id="sote",
        display_name="Sote-asiantuntija (v2)",
        category=DOMAIN_EXPERT,
        description="Mielenterveys- ja päihdeasiantuntija. Empaattinen ja trauma-informoitu ohjaus.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "sote_pack_v1"],
    ),
    "yhdenvertaisuus": AgentMetadata(
        id="yhdenvertaisuus",
        display_name="Yhdenvertaisuus-asiantuntija (v2)",
        category=DOMAIN_EXPERT,
        description="Antirasismi- ja yhdenvertaisuusasiantuntija. Keskittyy rakenteelliseen analyysiin.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "yhdenvertaisuus_pack_v1"],
    ),
    "koulutus": AgentMetadata(
        id="koulutus",
        display_name="Koulutussuunnittelija (v2)",
        category=DOMAIN_EXPERT,
        description="Pedagoginen asiantuntija. Suunnittelee osallistavia osallisuutta vahvistavia koulutuksia.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "koulutus_pack_v1"],
    ),
    "koulutus_draft": AgentMetadata(
        id="koulutus_draft",
        display_name="Koulutus-luonnostelija",
        category=DOMAIN_EXPERT,
        description="Koulutusrungon draftaus.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "koulutus_pack_v1"],
    ),
    "koulutus_refiner": AgentMetadata(
        id="koulutus_refiner",
        display_name="Koulutus-viilaaja",
        category=DOMAIN_EXPERT,
        description="Koulutusrungon hiominen.",
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
    "talous_data_reader": AgentMetadata(
        id="talous_data_reader",
        display_name="Talous-datan lukija",
        category=DOMAIN_EXPERT,
        description="Lukee talousdataa (Excel/CSV).",
        allowed_tools=FINANCE_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "talous_analyzer": AgentMetadata(
        id="talous_analyzer",
        display_name="Talous-analyytikko",
        category=DOMAIN_EXPERT,
        description="Analysoi talousdataa koodin avulla.",
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
    "lomakkeet_expert": AgentMetadata(
        id="lomakkeet_expert",
        display_name="Lomake-ammattilainen",
        category=DOMAIN_EXPERT,
        description="Lomakkeiden täyttö ja analyysi.",
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
        display_name="Tutkija (v2)",
        category=RESEARCH,
        description="Etsii tietoa monipuolisesti (RAG + Web). Faktantarkistus ja lähteet.",
        allowed_tools=RESEARCH_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "section_researcher": AgentMetadata(
        id="section_researcher",
        display_name="Syvähaun tutkija",
        category=RESEARCH,
        description="Sisäinen syvähaun tutkimusagentti (web-haku + viitteet).",
        allowed_tools=RESEARCH_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
        is_enabled=False,
    ),
    "enhanced_search_executor": AgentMetadata(
        id="enhanced_search_executor",
        display_name="Syvähaun jatkohaku",
        category=RESEARCH,
        description="Sisäinen syvähaun jatkotutkimusagentti.",
        allowed_tools=RESEARCH_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
        is_enabled=False,
    ),

    # OUTPUT
    "viestinta": AgentMetadata(
        id="viestinta",
        display_name="Viestintä (Some v2)",
        category=OUTPUT,
        description="Markkinointi, some-sisällöt ja visuaalien suunnittelu.",
        allowed_tools=CREATIVE_TOOLS + BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "viestinta_draft": AgentMetadata(
        id="viestinta_draft",
        display_name="Viestintä-luonnostelija",
        category=OUTPUT,
        description="Some-sisältöjen draftaus.",
        allowed_tools=CREATIVE_TOOLS + BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "viestinta_refiner": AgentMetadata(
        id="viestinta_refiner",
        display_name="Viestintä-viilaaja",
        category=OUTPUT,
        description="Some-sisältöjen ja CTA-osioiden hiominen.",
        allowed_tools=CREATIVE_TOOLS + BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "kirjoittaja": AgentMetadata(
        id="kirjoittaja",
        display_name="Kirjoittaja (v2)",
        category=OUTPUT,
        description="Dynaamisten tekstien, artikkeleiden ja raporttien ammattilainen.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "kirjoittaja_draft": AgentMetadata(
        id="kirjoittaja_draft",
        display_name="Kirjoittaja-luonnostelija",
        category=OUTPUT,
        description="Pitkien tekstien draftaus.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "kirjoittaja_refiner": AgentMetadata(
        id="kirjoittaja_refiner",
        display_name="Kirjoittaja-viilaaja",
        category=OUTPUT,
        description="Tekstien kielellinen ja sisällöllinen viilaus.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "grant_writer": AgentMetadata(
        id="grant_writer",
        display_name="Grant Writer (Field-Based v2)",
        category=OUTPUT,
        description="Rahoitushakemusten (STEA/EU) asiantuntija. Käyttää kenttäkohtaista QA-prosessia.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "project_planner": AgentMetadata(
        id="project_planner",
        display_name="Projektisuunnittelija (Strateginen)",
        category=LEADERSHIP,
        description="Tuottaa strategiset artefaktit (Logframe, Budget, Risks).",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "auto_template_analyzer": AgentMetadata(
        id="auto_template_analyzer",
        display_name="Pohja-analyytikko (v2)",
        category=OUTPUT,
        description="Analysoi hanke-pohjia ja lukitsee instrumentin (STEA/Erasmus).",
        allowed_tools=RESEARCH_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "field_writer": AgentMetadata(
        id="field_writer",
        display_name="Kenttä-kirjoittaja",
        category=OUTPUT,
        description="Kirjoittaa hakemuksen kenttä kerrallaan strategiaan pohjautuen.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "field_qa": AgentMetadata(
        id="field_qa",
        display_name="Kenttä-QA",
        category=OUTPUT,
        description="Tarkistaa kenttien laadun ja sääntöjenmukaisuuden.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "targeted_reviser": AgentMetadata(
        id="targeted_reviser",
        display_name="Täsmä-korjaaja",
        category=OUTPUT,
        description="Korjaa vain QA:n hylkäämät kentät.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
    ),
    "compliance_reporter": AgentMetadata(
        id="compliance_reporter",
        display_name="Säännöstenmukaisuus-raportoija",
        category=OUTPUT,
        description="Tuottaa lopullisen Compliance Reportin ja pisteytyksen.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "auto_writer_part1": AgentMetadata(
        id="auto_writer_part1",
        display_name="Hakemus-kirjoittaja (LEGACY 1)",
        category=OUTPUT,
        description="DEPRECATED: Vanha 11-osion kirjoittaja, osa 1.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
        is_enabled=False,
    ),
    "auto_writer_part2": AgentMetadata(
        id="auto_writer_part2",
        display_name="Hakemus-kirjoittaja (LEGACY 2)",
        category=OUTPUT,
        description="DEPRECATED: Vanha 11-osion kirjoittaja, osa 2.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
        is_enabled=False,
    ),
    "auto_writer_part3": AgentMetadata(
        id="auto_writer_part3",
        display_name="Hakemus-kirjoittaja (LEGACY 3)",
        category=OUTPUT,
        description="DEPRECATED: Vanha 11-osion kirjoittaja, osa 3.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
        is_enabled=False,
    ),
    "auto_finalizer": AgentMetadata(
        id="auto_finalizer",
        display_name="Hakemus-viimeistelijä (LEGACY)",
        category=OUTPUT,
        description="DEPRECATED: Vanha viimeistelijä.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "writer_pack_v1"],
        is_enabled=False,
    ),
    "auto_sote": AgentMetadata(
        id="auto_sote",
        display_name="Sote-validoija",
        category=DOMAIN_EXPERT,
        description="Varmistaa sote-sisällön laadun hakemuksessa.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "sote_pack_v1"],
    ),
    "auto_yhdenvertaisuus": AgentMetadata(
        id="auto_yhdenvertaisuus",
        display_name="Yhdenvertaisuus-validoija",
        category=DOMAIN_EXPERT,
        description="Varmistaa yhdenvertaisuus-sisällön laadun hakemuksessa.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "yhdenvertaisuus_pack_v1"],
    ),
    "auto_koulutus": AgentMetadata(
        id="auto_koulutus",
        display_name="Koulutus-validoija",
        category=DOMAIN_EXPERT,
        description="Varmistaa koulutus-sisällön laadun hakemuksessa.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1", "koulutus_pack_v1"],
    ),
    "auto_reviewer": AgentMetadata(
        id="auto_reviewer",
        display_name="Automaattinen arvioija",
        category=OUTPUT,
        description="Suorittaa automaattisen laaduntarkistuksen hakemukselle.",
        allowed_tools=RESEARCH_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
    ),
    "final_assembly": AgentMetadata(
        id="final_assembly",
        display_name="Lopullinen kokoonpano",
        category=OUTPUT,
        description="Yhdistää hakemuksen osat yhdeksi dokumentiksi.",
        allowed_tools=BASIC_TOOLS,
        prompt_pack_versions=["org_pack_v1"],
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
