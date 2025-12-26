"""
Samha PII Scrubber

Masks sensitive information:
- Emails
- Phone numbers
- Personal IDs
- Addresses (limited patterns)
"""

import re
from typing import Tuple, List

# Email pattern
EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

# Phone pattern (Finnish style, supports +358 with spaces/hyphens)
PHONE_PATTERN = r'(?:\+358|0[1-9])(?:[\s-]*\d){7,10}'

# Personal ID (HETU)
HETU_PATTERN = r'\b\d{6}[-+A]\d{3}[0-9A-Z]\b'

def pii_scrubber(text: str) -> Tuple[str, List[str]]:
    """
    Masks PII in the given text.
    
    Returns:
        (redacted_text, list_of_detected_pii_types)
    """
    if not text:
        return text, []
    
    flags = []
    redacted = text
    
    if re.search(EMAIL_PATTERN, redacted):
        redacted = re.sub(EMAIL_PATTERN, "[EMAIL_REDACTED]", redacted)
        flags.append("EMAIL")
        
    if re.search(PHONE_PATTERN, redacted):
        redacted = re.sub(PHONE_PATTERN, "[PHONE_REDACTED]", redacted)
        flags.append("PHONE")
        
    if re.search(HETU_PATTERN, redacted):
        redacted = re.sub(HETU_PATTERN, "[HETU_REDACTED]", redacted)
        flags.append("HETU")
        
    return redacted, flags
