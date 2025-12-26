"""
Egress Middleware for Samha.
Ensures no PII leaves the system boundary.
"""
from typing import Optional
from urllib.parse import urlparse
import re

from app.pii_scrubber import pii_scrubber

CITE_TAG_RE = re.compile(r'<cite\s+source\s*=\s*["\']?\s*(src-\d+)\s*["\']?\s*/>')
FINNISH_CITE_RE = re.compile(r'\[Lähde\s+(src-\d+)\]')
MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s)]+)\)')

def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return url

def _sources_from_links(text: str) -> dict:
    sources = {}
    url_to_id = {}
    next_id = 1
    for match in MD_LINK_RE.finditer(text or ""):
        title = match.group(1).strip()
        url = match.group(2).strip()
        if url in url_to_id:
            continue
        short_id = f"src-{next_id}"
        next_id += 1
        sources[short_id] = {
            "short_id": short_id,
            "title": title or _domain_from_url(url),
            "url": url,
            "domain": _domain_from_url(url),
            "supported_claims": [],
        }
        url_to_id[url] = short_id
    return sources

def _replace_cite_tags_with_links(text: str, sources: dict) -> str:
    if not text:
        return ""
    def replacer(match: re.Match) -> str:
        short_id = match.group(1)
        source_info = sources.get(short_id) if isinstance(sources, dict) else None
        if not source_info:
            return match.group(0)
        label = source_info.get("title") or source_info.get("domain") or short_id
        url = source_info.get("url")
        if url:
            return f" [{label}]({url})"
        return f" [{label}]"
    # Replace XML-style cite tags
    result = CITE_TAG_RE.sub(replacer, text)
    # Also replace Finnish-style [Lähde src-X] citations
    result = FINNISH_CITE_RE.sub(replacer, result)
    return result

def ensure_sources_payload(state: dict, final_text: str) -> None:
    """
    Ensure sources are available for UI (structured map + optional cited report).
    Also updates final_response with clickable citation links.
    """
    if not isinstance(state, dict):
        return
    sources = state.get("sources")
    if not isinstance(sources, dict) or not sources:
        try:
            from app.deep_search import _ensure_sources_from_state
            sources = _ensure_sources_from_state(state)
        except Exception:
            sources = {}
    if not sources:
        sources = _sources_from_links(final_text)
        if sources:
            state["sources"] = sources
    if sources:
        linked_text = _replace_cite_tags_with_links(final_text, sources)
        state["final_report_with_citations"] = linked_text
        # Also update final_response so frontend gets linked version
        state["final_response"] = linked_text

def scrub_for_user(text: str) -> str:
    """
    Final egress PII scrub.
    MUST be called before returning content to user.
    """
    if not text:
        return ""
    
    # Run the regex-based scrubber
    scrubbed, _ = pii_scrubber(text)
    
    return scrubbed

def egress_handler(response_text: str, session_state: dict = None) -> str:
    """
    Orchestrates egress processing.
    """
    # 1. PII Scrub
    safe_text = scrub_for_user(response_text)
    
    # 2. (Optional) Audit log
    # log_egress(safe_text)
    
    return safe_text
