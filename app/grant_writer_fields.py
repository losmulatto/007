"""
Grant Writer Field-Based Architecture

Core principle: NO TEMPLATE, NO WRITE
Writer only writes to fields defined in funder_requirements.

This module provides:
1. Field extraction from templates (PDF or RAG)
2. Universal content mappings (what each field type needs)
3. Field-level validation
4. Compliance report generation
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import json
import re


class FieldType(str, Enum):
    """Universal field type classification."""
    SUMMARY = "summary"
    NEEDS = "needs"
    OBJECTIVES = "objectives"
    TARGET_GROUP = "target_group"
    IMPLEMENTATION = "implementation"
    TIMELINE = "timeline"
    MONITORING = "monitoring"
    IMPACT = "impact"
    SUSTAINABILITY = "sustainability"
    BUDGET = "budget"
    SOURCES = "sources"
    OTHER = "other"


@dataclass
class FieldRequirement:
    """Single field extracted from funder template."""
    field_id: str
    title: str
    min_chars: int = 0
    max_chars: int = 10000
    guidance: str = ""
    scoring_weight: int = 0
    field_type: FieldType = FieldType.OTHER
    required_anchors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "field_id": self.field_id,
            "title": self.title,
            "min_chars": self.min_chars,
            "max_chars": self.max_chars,
            "guidance": self.guidance,
            "scoring_weight": self.scoring_weight,
            "field_type": self.field_type.value,
            "required_anchors": self.required_anchors
        }


@dataclass
class FunderRequirements:
    """Complete template structure from funder."""
    funder: str
    instrument: str
    instrument_type: str  # e.g., "KA152-YOU", "KA153-YOU", "STEA-C"
    fields: List[FieldRequirement] = field(default_factory=list)
    non_negotiables: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "funder": self.funder,
            "instrument": self.instrument,
            "instrument_type": self.instrument_type,
            "fields": [f.to_dict() for f in self.fields],
            "non_negotiables": self.non_negotiables
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# =============================================================================
# UNIVERSAL CONTENT REQUIREMENTS PER FIELD TYPE
# =============================================================================
# What each field type MUST contain

UNIVERSAL_CONTENT_REQUIREMENTS = {
    FieldType.SUMMARY: {
        "required": ["project_name", "main_goal", "target_group", "duration"],
        "anchors": [],
        "guidance": "Tiivistä hankkeen ydin 2-3 lauseessa"
    },
    FieldType.NEEDS: {
        "required": ["statistics", "target_group_description", "why_now", "gap_analysis"],
        "anchors": ["number", "percentage", "source", "year"],
        "guidance": "Perustele tarve tilastoilla ja tutkimuksella"
    },
    FieldType.OBJECTIVES: {
        "required": ["smart_objectives", "indicators", "baseline", "target_values"],
        "anchors": ["number", "percentage", "date"],
        "guidance": "SMART-tavoitteet taulukkona"
    },
    FieldType.TARGET_GROUP: {
        "required": ["who", "how_many", "selection_criteria", "recruitment"],
        "anchors": ["number"],
        "guidance": "Kuvaa kohderyhmä tarkasti"
    },
    FieldType.IMPLEMENTATION: {
        "required": ["activities", "methods", "responsibilities", "frequency"],
        "anchors": ["date", "number"],
        "guidance": "Jokainen toimenpide erikseen"
    },
    FieldType.TIMELINE: {
        "required": ["phases", "milestones", "dates"],
        "anchors": ["date", "month", "quarter"],
        "guidance": "Aikataulu kvartaali- tai kuukausitasolla"
    },
    FieldType.MONITORING: {
        "required": ["indicators", "data_collection", "frequency", "responsibility"],
        "anchors": ["number", "percentage"],
        "guidance": "Miten tuloksia seurataan"
    },
    FieldType.IMPACT: {
        "required": ["short_term", "long_term", "structural", "dissemination"],
        "anchors": [],
        "guidance": "Vaikutukset eri aikajänteillä"
    },
    FieldType.SUSTAINABILITY: {
        "required": ["continuation", "resources", "scaling"],
        "anchors": [],
        "guidance": "Miten toiminta jatkuu rahoituksen jälkeen"
    },
    FieldType.BUDGET: {
        "required": ["categories", "amounts", "justifications"],
        "anchors": ["number", "euro"],
        "guidance": "Kustannuserittely ja perustelut"
    },
    FieldType.SOURCES: {
        "required": ["references"],
        "anchors": ["url", "year"],
        "guidance": "Kaikki käytetyt lähteet"
    }
}


# =============================================================================
# FIELD TYPE CLASSIFIER
# =============================================================================

def classify_field_type(title: str, guidance: str = "") -> FieldType:
    """
    Classify field type based on title and guidance text.
    Uses heuristics to map to universal field types.
    """
    text = (title + " " + guidance).lower()
    
    # Title-based classification
    if any(kw in text for kw in ["tiivistelmä", "summary", "abstract", "yhteenveto"]):
        return FieldType.SUMMARY
    if any(kw in text for kw in ["tarve", "need", "tausta", "background", "context", "relevance"]):
        return FieldType.NEEDS
    if any(kw in text for kw in ["tavoite", "objective", "goal", "aim", "päämäärä"]):
        return FieldType.OBJECTIVES
    if any(kw in text for kw in ["kohderyhmä", "target", "participant", "osallistuja"]):
        return FieldType.TARGET_GROUP
    if any(kw in text for kw in ["toimenpide", "activity", "action", "implementation", "toteutus", "menetelmä", "method"]):
        return FieldType.IMPLEMENTATION
    if any(kw in text for kw in ["aikataulu", "timeline", "schedule", "calendar"]):
        return FieldType.TIMELINE
    if any(kw in text for kw in ["seuranta", "monitor", "indicator", "mittari", "evaluation"]):
        return FieldType.MONITORING
    if any(kw in text for kw in ["vaikut", "impact", "result", "tulos", "outcome"]):
        return FieldType.IMPACT
    if any(kw in text for kw in ["kestävyys", "sustain", "jatkuvuus", "continuation"]):
        return FieldType.SUSTAINABILITY
    if any(kw in text for kw in ["budjetti", "budget", "cost", "kustannus", "talous"]):
        return FieldType.BUDGET
    if any(kw in text for kw in ["lähde", "source", "reference", "viite"]):
        return FieldType.SOURCES
    
    return FieldType.OTHER


# =============================================================================
# FIELD VALIDATION
# =============================================================================

@dataclass
class FieldValidationResult:
    """Result of validating a single field."""
    field_id: str
    is_valid: bool
    char_count: int
    chars_ok: bool
    missing_anchors: List[str]
    issues: List[str]
    fix_suggestions: List[str]
    
    def to_dict(self) -> dict:
        return {
            "field_id": self.field_id,
            "is_valid": self.is_valid,
            "char_count": self.char_count,
            "chars_ok": self.chars_ok,
            "missing_anchors": self.missing_anchors,
            "issues": self.issues,
            "fix_suggestions": self.fix_suggestions
        }


def validate_field(
    field_req: FieldRequirement,
    content: str
) -> FieldValidationResult:
    """
    Validate a single field's content against requirements.
    
    Checks:
    1. Character count within limits
    2. Required anchors present (numbers, dates, sources)
    3. Universal content requirements for field type
    """
    issues = []
    fix_suggestions = []
    missing_anchors = []
    
    # 1. Character count
    char_count = len(content)
    chars_ok = field_req.min_chars <= char_count <= field_req.max_chars
    
    if char_count < field_req.min_chars:
        issues.append(f"Too short: {char_count}/{field_req.min_chars} chars")
        fix_suggestions.append(f"Add {field_req.min_chars - char_count} more characters")
    elif char_count > field_req.max_chars:
        issues.append(f"Too long: {char_count}/{field_req.max_chars} chars")
        fix_suggestions.append(f"Reduce by {char_count - field_req.max_chars} characters")
    
    # 2. Required anchors
    anchor_patterns = {
        "number": r'\d+',
        "percentage": r'\d+\s*%',
        "date": r'\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}',
        "year": r'20\d{2}',
        "euro": r'€|\d+\s*euroa?',
        "url": r'https?://|www\.',
        "source": r'\([^)]+,\s*\d{4}\)|lähde:|source:'
    }
    
    # Get required anchors for this field type
    field_type_reqs = UNIVERSAL_CONTENT_REQUIREMENTS.get(
        field_req.field_type, 
        {"anchors": []}
    )
    required_anchors = field_req.required_anchors or field_type_reqs.get("anchors", [])
    
    for anchor in required_anchors:
        pattern = anchor_patterns.get(anchor)
        if pattern and not re.search(pattern, content, re.IGNORECASE):
            missing_anchors.append(anchor)
            issues.append(f"Missing anchor: {anchor}")
            fix_suggestions.append(f"Add at least one {anchor}")
    
    # 3. Determine validity
    is_valid = chars_ok and len(missing_anchors) == 0
    
    return FieldValidationResult(
        field_id=field_req.field_id,
        is_valid=is_valid,
        char_count=char_count,
        chars_ok=chars_ok,
        missing_anchors=missing_anchors,
        issues=issues,
        fix_suggestions=fix_suggestions
    )


# =============================================================================
# COMPLIANCE REPORT
# =============================================================================

@dataclass 
class ComplianceReport:
    """Final compliance report for user."""
    total_fields: int
    valid_fields: int
    failed_fields: List[FieldValidationResult]
    total_chars: int
    has_critical_issues: bool
    summary: str
    
    def to_markdown(self) -> str:
        """Generate user-friendly compliance report."""
        lines = [
            "# 📋 Compliance Report",
            "",
            f"**Kentät:** {self.valid_fields}/{self.total_fields} OK",
            f"**Merkkimäärä:** {self.total_chars:,}",
            f"**Tila:** {'✅ VALMIS' if not self.has_critical_issues else '⚠️ KORJATTAVAA'}",
            ""
        ]
        
        if self.failed_fields:
            lines.append("## ⚠️ Korjattavat kentät")
            lines.append("")
            for f in self.failed_fields:
                lines.append(f"### {f.field_id}")
                lines.append(f"- Merkit: {f.char_count}")
                for issue in f.issues:
                    lines.append(f"- ❌ {issue}")
                for fix in f.fix_suggestions:
                    lines.append(f"- 💡 {fix}")
                lines.append("")
        
        return "\n".join(lines)


def generate_compliance_report(
    requirements: FunderRequirements,
    field_contents: Dict[str, str]
) -> ComplianceReport:
    """Generate full compliance report."""
    results = []
    failed = []
    total_chars = 0
    
    for field_req in requirements.fields:
        content = field_contents.get(field_req.field_id, "")
        result = validate_field(field_req, content)
        results.append(result)
        total_chars += result.char_count
        
        if not result.is_valid:
            failed.append(result)
    
    valid_count = len(results) - len(failed)
    has_critical = len(failed) > 0
    
    if has_critical:
        summary = f"{len(failed)} kenttää vaatii korjausta"
    else:
        summary = "Kaikki kentät OK - valmis lähetettäväksi"
    
    return ComplianceReport(
        total_fields=len(results),
        valid_fields=valid_count,
        failed_fields=failed,
        total_chars=total_chars,
        has_critical_issues=has_critical,
        summary=summary
    )
