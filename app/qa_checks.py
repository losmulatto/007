import re
from typing import List, Dict, Any

NUMERIC_PATTERNS = [
    r"\b\d{1,3}(?:[ \u00A0]\d{3})*(?:,\d+)?\s*€\b",  # 1 234,56 €
    r"\b\d+(?:,\d+)?\s*%\b",                        # 12,5 %
    r"\b20\d{2}\b",                                 # 2024
    r"\bn\s*=\s*\d+\b",                             # n=30
]

def _contains_numeric_claim(text: str) -> bool:
    for p in NUMERIC_PATTERNS:
        if re.search(p, text):
            return True
    return False

def finance_numeric_integrity_check(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload = {
      "agent_name": "...",
      "domain": "...",
      "detailed_content": "...",
      "facts": [...],
      "metadata": {"tool_calls": [...], "rag_used": bool, ...}
    }
    """
    content = payload.get("detailed_content") or payload.get("content") or ""
    facts = payload.get("facts") or []
    metadata = payload.get("metadata") or {}
    tool_calls: List[str] = metadata.get("tool_calls") or []
    # If tool_calls are list of dicts (standard in some versions)
    if tool_calls and isinstance(tool_calls[0], dict):
        tool_names = [tc.get("name") for tc in tool_calls]
    else:
        tool_names = tool_calls

    # tarkistus koskee talousagenttia ja myös kaikkia outputteja, joissa on talousnumeroita
    if not _contains_numeric_claim(content):
        return {"passed": True, "severity": "info", "issue": None}

    # vaadi laskentajälki (python/pandas tai excel-analyysi) tai rag-lähde (jos kyse on sisäisestä raportista)
    has_calc_tool = any(t in tool_names for t in ["python", "read_excel", "analyze_excel_summary"])
    if not has_calc_tool:
        return {
            "passed": False,
            "severity": "critical",
            "issue": "numeroväitteitä ilman python/excel-laskentajälkeä",
            "fix_suggestion": "aja python/pandas analyysi (tai read_excel+analyze_excel_summary) ja lisää kaikki luvut facts-listaan"
        }

    # factitem-kuri: talousnumerot eivät saa tulla prompt/none-lähteestä
    bad_sources = [f for f in facts if f.get("source") in ("prompt", "none")]
    if bad_sources:
        return {
            "passed": False,
            "severity": "critical",
            "issue": "facts-listassa talouslukuja lähteellä prompt/none",
            "fix_suggestion": "vaihda lähteet python/rag/web ja lisää source_url tai raportti-id jos saatavilla"
        }

    return {"passed": True, "severity": "info", "issue": None}
