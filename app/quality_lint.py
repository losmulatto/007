from typing import Dict, Any, List

VAGUE_PHRASES = [
    "toiminta sujui hyvin",
    "lisätään tietoisuutta",
    "tuetaan osallistujia",
    "kehitetään yhteistyötä",
    "edistetään hyvinvointia"
]

import re

VAGUE_PHRASES = [
    "toiminta sujui hyvin",
    "lisätään tietoisuutta",
    "tuetaan osallistujia",
    "kehitetään yhteistyötä",
    "edistetään hyvinvointia"
]

ANCHOR_PATTERNS = [
    r"\d+",           # Numbers
    r"€|%|n=",        # Units/Metrics
    r"klo",           # Time
    r"pvm|kk",        # Date/Month signals
    r"tavoite|mittari" # Specific context words
]

def lint_quality(text: str) -> Dict[str, Any]:
    """
    Checks text for vague phrases without anchors.
    An anchor is a number, specific unit, or concrete context word.
    """
    lower_text = text.lower()
    issues = []
    
    # Split text into sentences for localized anchor check
    sentences = re.split(r'[.!?]\s+', text)
    
    for phrase in VAGUE_PHRASES:
        if phrase in lower_text:
            # Found a vague phrase, now look for an anchor in the same sentence
            phrase_found_without_anchor = False
            for sentence in sentences:
                s_lower = sentence.lower()
                if phrase in s_lower:
                    has_anchor = any(re.search(p, s_lower) for p in ANCHOR_PATTERNS)
                    if not has_anchor:
                        phrase_found_without_anchor = True
                        break
            
            if phrase_found_without_anchor:
                issues.append(f"Vague phrase without anchor: '{phrase}'")
            
    if issues:
        return {
            "passed": False,
            "issues": issues, 
            "severity": "critical",
            "fix_suggestion": "Replace vague phrases with concrete actions (who, what, when, how)."
        }
        
    return {"passed": True, "issues": [], "severity": "info"}
