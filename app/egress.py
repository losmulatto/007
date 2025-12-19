"""
Egress Middleware for Samha.
Ensures no PII leaves the system boundary.
"""
from typing import Optional
from app.pii_scrubber import pii_scrubber

def scrub_for_user(text: str) -> str:
    """
    Final egress PII scrub.
    MUST be called before returning content to user.
    """
    if not text:
        return ""
    
    # Run the regex-based scrubber
    scrubbed = pii_scrubber(text)
    
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
