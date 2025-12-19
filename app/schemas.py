"""
Samha Agent Schemas v1.1 - Production-Ready Contracts

CHANGELOG:
- v1.1: Span tracing, validators, section models, computed fields, claim taxonomy
- v1.0: Initial production schemas

Kaikki agentit käyttävät näitä yhtenäisiä skeemoja.
"""

from pydantic import BaseModel, Field, field_validator, model_validator, computed_field
from typing import List, Optional, Literal, Any
from datetime import datetime, date, timezone
import uuid
import re
import hashlib


# =============================================================================
# UTILITY TYPES
# =============================================================================

IntentType = Literal["question", "planning", "writing", "advice", "qa", "routing", "crisis"]
ToneType = Literal["empaattinen", "asiallinen", "virallinen", "kannustava", "neutraali"]
AudienceType = Literal["asiakas", "viranomainen", "kumppani", "sisäinen", "nuori", "ammattilainen"]
LanguageType = Literal["fi", "en", "sv"]
ClaimType = Literal["number", "date", "person", "policy_requirement", "definition", "general_advice", "opinion"]
SourceType = Literal["rag", "web", "prompt", "none"]
SeverityType = Literal["critical", "warning", "info"]


# =============================================================================
# TOOL CALL TRACING
# =============================================================================

class ToolCall(BaseModel):
    """Strukturoitu työkalukutsu jäljitystä varten."""
    name: str = Field(..., description="Työkalun nimi")
    status: Literal["success", "error", "timeout"] = Field(...)
    latency_ms: int = Field(..., description="Kesto millisekunteina")
    input_hash: Optional[str] = Field(None, description="Syötteen hash (debug)")
    output_ref: Optional[str] = Field(None, description="Viite tulosteeseen")
    cost_tokens: Optional[int] = Field(None, description="Käytetyt tokenit jos saatavilla")
    error_message: Optional[str] = Field(None)


# =============================================================================
# FACT ITEM - Lähdekurinalaisuus
# =============================================================================

class FactItem(BaseModel):
    """Yksittäinen fakta ja sen lähde - VALIDOITU."""
    claim: str = Field(..., description="Väite tai tieto")
    claim_type: ClaimType = Field(..., description="Väitteen tyyppi")
    source: SourceType = Field(..., description="Mistä tieto tuli")
    source_url: Optional[str] = Field(None, description="URL tai dokumentin ID")
    source_date: Optional[str] = Field(None, description="Lähteen päivämäärä")
    source_excerpt: Optional[str] = Field(None, description="Lyhyt ote lähteestä")
    confidence: Literal["high", "medium", "low"] = Field("medium")
    
    @field_validator("source_url", mode="before")
    @classmethod
    def validate_source_url_required(cls, v, info):
        """web/rag vaatii source_url:n."""
        source = info.data.get("source")
        if source in ["web", "rag"] and not v:
            raise ValueError(f"source_url is required when source is '{source}'")
        return v
    
    @model_validator(mode="after")
    def validate_source_integrity(self):
        """Tarkista lähdekurinalaisuus."""
        # web/rag vaatii date
        if self.source in ["web", "rag"] and not self.source_date:
            raise ValueError(f"source_date is required when source is '{self.source}'")
        
        # Kriittiset claim_typet vaativat lähteen
        critical_types = ["number", "date", "person", "policy_requirement"]
        if self.claim_type in critical_types and self.source == "none":
            if self.confidence == "high":
                raise ValueError(f"claim_type '{self.claim_type}' with source='none' cannot have confidence='high'")
        
        return self


# =============================================================================
# AGENT METADATA - Jäljitettävyys
# =============================================================================

class AgentMetadata(BaseModel):
    """Jokaisen vastauksen metadata - PAKOLLINEN."""
    # Trace chain (root luo trace_id, muut perii)
    trace_id: str = Field(..., description="Jäljitys-ID koko ketjulle - ROOT luo, muut perii")
    span_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="Tämän agentin span")
    parent_span_id: Optional[str] = Field(None, description="Edellisen agentin span")
    
    # Agent info
    agent_name: str = Field(..., description="Mikä agentti tuotti tämän")
    prompt_packs: List[str] = Field(..., description="Käytetyt prompt-paketit, esim. ['org_pack_v1', 'sote_pack_v1']")
    
    # Timing
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Tool usage
    tool_calls: List[ToolCall] = Field(default_factory=list)
    rag_used: bool = Field(False)
    web_used: bool = Field(False)
    
    @computed_field
    @property
    def tool_call_count(self) -> int:
        return len(self.tool_calls)
    
    @computed_field
    @property
    def total_tool_latency_ms(self) -> int:
        return sum(tc.latency_ms for tc in self.tool_calls)


# =============================================================================
# HARD GATES - Pakotettu RAG/Web
# =============================================================================

class HardGateSignals(BaseModel):
    """Signaalit jotka pakottavat RAG/Web-haun."""
    
    # Numeric/temporal signals
    contains_year: bool = Field(False)
    contains_money: bool = Field(False)
    contains_percentage: bool = Field(False)
    contains_count: bool = Field(False)
    contains_relative_time: bool = Field(False, description="viime vuonna, tänä keväänä, jne.")
    
    # Entity signals
    contains_person_name: bool = Field(False)
    contains_organization: bool = Field(False)
    contains_project_code: bool = Field(False)
    
    # Question signals
    asks_who: bool = Field(False)
    asks_how_much: bool = Field(False)
    asks_when: bool = Field(False)
    asks_official_requirement: bool = Field(False)
    
    # Computed results (serialized for QA visibility)
    rag_required: bool = Field(False)
    web_required: bool = Field(False)
    
    @model_validator(mode="after")
    def compute_requirements(self):
        """Laske rag_required ja web_required."""
        self.rag_required = any([
            self.contains_year,
            self.contains_money,
            self.contains_percentage,
            self.contains_count,
            self.contains_relative_time,
            self.contains_person_name,
            self.contains_organization,
            self.contains_project_code,
            self.asks_who,
            self.asks_how_much,
            self.asks_when,
        ])
        self.web_required = self.asks_official_requirement
        return self


class GateDecision(BaseModel):
    """Hard gate -päätös ja mahdolliset rikkomukset."""
    signals: HardGateSignals
    decision: Literal["rag_required", "web_required", "both_required", "no_gate"] = Field(...)
    gate_satisfied: bool = Field(..., description="Täytettiinkö gate-vaatimukset")
    violations: List[str] = Field(default_factory=list, description="Mitä gateä rikottiin")


# =============================================================================
# SECTION MODELS - Rakenteinen sisältö
# =============================================================================

class TrainingSection(BaseModel):
    """Koulutuksen osio."""
    title: str = Field(..., description="Osion otsikko")
    duration_minutes: int = Field(..., description="Kesto minuutteina")
    method: str = Field(..., description="Menetelmä (osallistava, luento, jne.)")
    description: str = Field(..., description="Kuvaus")
    materials: List[str] = Field(default_factory=list)


class DocumentSection(BaseModel):
    """Dokumentin/hakemuksen osio."""
    heading: str = Field(..., description="Otsikko")
    content: str = Field(..., description="Sisältö")
    word_count: int = Field(0)
    
    @model_validator(mode="after")
    def compute_word_count(self):
        self.word_count = len(self.content.split())
        return self


# =============================================================================
# BASE AGENT RESPONSE
# =============================================================================

class BaseAgentResponse(BaseModel):
    """Pohja kaikille agenttivastauksille."""
    metadata: AgentMetadata
    
    # Intent & context
    intent: IntentType = Field(...)
    audience: AudienceType = Field("asiakas")
    language: LanguageType = Field("fi")
    
    # Hard gates (näkyy QA:lle)
    hard_gates: Optional[GateDecision] = Field(None)
    
    # Content
    facts: List[FactItem] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    needs_user_input: List[str] = Field(default_factory=list)
    
    # Style
    tone: ToneType = Field("empaattinen")
    
    @computed_field
    @property
    def content_hash(self) -> str:
        """Hash sisällöstä QA-linkitystä varten."""
        content = str(self.facts) + str(self.recommendations)
        return hashlib.md5(content.encode()).hexdigest()[:12]


# =============================================================================
# DOMAIN-SPECIFIC SCHEMAS
# =============================================================================

class ExpertResponse(BaseAgentResponse):
    """SOTE/Yhdenvertaisuus-asiantuntijan vastaus."""
    domain: Literal["sote", "yhdenvertaisuus", "koulutus", "hr", "talous"] = Field(...)
    summary: str = Field(...)
    detailed_content: str = Field(...)
    
    # Domain-specific
    service_guidance: Optional[str] = Field(None, description="Palveluohjaus")
    crisis_indicators: List[str] = Field(default_factory=list)
    

class TrainingPlan(BaseAgentResponse):
    """Koulutussuunnittelijan tuottama suunnitelma."""
    title: str = Field(...)
    duration_total: str = Field(..., description="Kokonaiskesto")
    target_audience: str = Field(...)
    learning_objectives: List[str] = Field(...)
    
    # Structured sections
    sections: List[TrainingSection] = Field(...)
    
    # Methods & materials
    methods_used: List[str] = Field(...)
    materials_needed: List[str] = Field(default_factory=list)
    
    # Samha connection
    samha_values_applied: List[str] = Field(...)
    
    @computed_field
    @property
    def total_duration_minutes(self) -> int:
        return sum(s.duration_minutes for s in self.sections)


class GrantDraft(BaseAgentResponse):
    """Grant Writer -agentin tuottama hakemusluonnos."""
    document_type: Literal["stea_hakemus", "stea_raportti", "erasmus_hakemus", "muu"] = Field(...)
    title: str = Field(...)
    
    # Structured sections
    sections: List[DocumentSection] = Field(...)
    
    # Key figures with STRICT source requirements
    key_figures: List[FactItem] = Field(...)
    
    # Character limit (set by coordinator based on document_type)
    character_limit: Optional[int] = Field(None)
    
    @computed_field
    @property
    def word_count(self) -> int:
        return sum(s.word_count for s in self.sections)
    
    @computed_field
    @property
    def character_count(self) -> int:
        return sum(len(s.content) for s in self.sections)
    
    @computed_field
    @property
    def character_limit_ok(self) -> bool:
        if self.character_limit is None:
            return True
        return self.character_count <= self.character_limit
    
    @model_validator(mode="after")
    def validate_key_figures_sources(self):
        """Key figures MUST have sources."""
        for fig in self.key_figures:
            if fig.claim_type in ["number", "date", "person"] and fig.source == "none":
                raise ValueError(f"key_figure '{fig.claim}' must have a source (not 'none')")
        return self


class ArticleDraft(BaseAgentResponse):
    """Kirjoittajan tuottama artikkeli/viesti."""
    format: Literal["blog", "some", "email", "report", "internal_memo"] = Field(...)
    title: str = Field(...)
    content: str = Field(...)
    
    readability_level: Literal["selkokieli", "yleiskieli", "ammattikieli"] = Field("yleiskieli")
    
    @computed_field
    @property
    def word_count(self) -> int:
        return len(self.content.split())


# =============================================================================
# QA/POLICY - Turvakerros
# =============================================================================

class QACheckResult(BaseModel):
    """Yksittäisen tarkistuksen tulos."""
    check_name: str = Field(...)
    passed: bool = Field(...)
    severity: SeverityType = Field(...)
    issue: Optional[str] = Field(None)
    fix_suggestion: Optional[str] = Field(None)


class RevisionTarget(BaseModel):
    """Korjausosoite revision loopille."""
    agent_name: str = Field(...)
    issue: str = Field(...)
    fix_instruction: str = Field(...)
    severity: SeverityType = Field(...)


class QAReport(BaseModel):
    """QA/Policy-agentin tarkistusraportti."""
    # Linkitys
    trace_id: str = Field(...)
    checked_agent_name: str = Field(..., description="Mikä agentti tuotti tarkistetun sisällön")
    checked_output_hash: str = Field(..., description="Tarkistetun sisällön hash")
    
    # Timing
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Decision (auto-computed from checks)
    decision: Literal["APPROVE", "REJECT", "NEEDS_REVISION"] = Field(...)
    
    # Checks
    checks: List[QACheckResult] = Field(...)
    
    # Category summaries
    sote_safety_pass: bool = Field(...)
    privacy_pass: bool = Field(...)
    anti_racism_pass: bool = Field(...)
    source_integrity_pass: bool = Field(...)
    tone_pass: bool = Field(...)
    
    # Issues
    critical_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    
    # Revision loop
    revision_targets: List[RevisionTarget] = Field(default_factory=list)
    
    @model_validator(mode="after")
    def auto_reject_critical(self):
        """Kriittinen fail => REJECT automaattisesti."""
        critical_categories = [
            self.sote_safety_pass,
            self.privacy_pass,
            self.anti_racism_pass,
            self.source_integrity_pass,
        ]
        if not all(critical_categories):
            if self.decision == "APPROVE":
                raise ValueError("Cannot APPROVE with critical category failures")
        return self


# =============================================================================
# PROMPT PACKS - Versioidut konfiguraatiot
# =============================================================================

class PromptPackInfo(BaseModel):
    """Prompt-paketin metatiedot."""
    name: str = Field(...)
    version: str = Field(...)
    effective_from: date = Field(...)
    last_updated: date = Field(...)
    description: str = Field(...)
    changelog: List[str] = Field(default_factory=list)
    approved_by: Optional[str] = Field(None, description="Kuka hyväksyi (turvallisuus/ääni)")


# Active prompt packs (päivitetään säännöllisesti)
PROMPT_PACKS = {
    "org_pack_v1": PromptPackInfo(
        name="org_pack",
        version="v1",
        effective_from=date(2024, 12, 17),
        last_updated=date(2024, 12, 17),
        description="Samhan missio, arvot, ääni, palvelulupaus",
        changelog=["v1: Initial release"],
    ),
    "sote_pack_v1": PromptPackInfo(
        name="sote_pack",
        version="v1",
        effective_from=date(2024, 12, 17),
        last_updated=date(2024, 12, 17),
        description="SOTE-turvallisuus, palveluohjaus, kriisikriteerit",
        changelog=["v1: Initial release"],
    ),
    "yhdenvertaisuus_pack_v1": PromptPackInfo(
        name="yhdenvertaisuus_pack",
        version="v1",
        effective_from=date(2024, 12, 17),
        last_updated=date(2024, 12, 17),
        description="Kieli, intersektionaalisuus, antirasmi-tarkistuslista",
        changelog=["v1: Initial release"],
    ),
    "writer_pack_v1": PromptPackInfo(
        name="writer_pack",
        version="v1",
        effective_from=date(2024, 12, 17),
        last_updated=date(2024, 12, 17),
        description="Rakenne, tyyli, saavutettavuus, Stea-muoto",
        changelog=["v1: Initial release"],
    ),
}


# =============================================================================
# WEB ALLOWLIST - Ulkoiset lähteet
# =============================================================================

WEB_ALLOWLIST = {
    "stea": ["stea.fi", "avustukset.stea.fi"],
    "sote": ["thl.fi", "valvira.fi", "kela.fi", "mielenterveystalo.fi"],
    "erasmus": ["erasmusplus.fi", "oph.fi", "ec.europa.eu/programmes/erasmus-plus"],
    "legal": ["finlex.fi", "eduskunta.fi"],
    "statistics": ["stat.fi", "tilastokeskus.fi"],
}
