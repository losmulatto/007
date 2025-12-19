"""
Samha Hard Gate Middleware

Tämä moduuli pakottaa RAG/Web-haun ENNEN kuin agentti saa vastata.
Gates are enforced by code, not by prompt wishes.

Käyttö:
    signals = detect_gate_signals(user_message)
    decision = enforce_gates(signals, rag_result, web_result)
    if not decision.gate_satisfied:
        # Älä anna agentin vastata - pakota haku ensin
"""

import re
from typing import Optional, List, Tuple
from app.schemas import HardGateSignals, GateDecision


# =============================================================================
# SIGNAL DETECTION - Suomenkielinen NLP-pohjainen tunnistus
# =============================================================================

# Vuosiluvut
YEAR_PATTERNS = [
    r'\b(19|20)\d{2}\b',  # 1990-2099
    r'\bviime vuonna\b',
    r'\btänä vuonna\b',
    r'\bviime kaudella\b',
    r'\btänä keväänä\b',
    r'\bviime syksynä\b',
    r'\bviime kuussa\b',
    r'\btänä kuukautena\b',
    r'\bensi vuonna\b',
]

# Rahasummat
MONEY_PATTERNS = [
    r'\d+\s*€',
    r'\d+\s*euroa?\b',
    r'\bbudjetti\b',
    r'\bavustus\b',
    r'\brahoitus\b',
    r'\bkustannus\b',
    r'\bhinta\b',
    r'\btonnia\b',  # "pari tonnia"
    r'\btuhatta\b',
    r'\bmiljoonaa?\b',
]

# Prosentit ja luvut
PERCENTAGE_PATTERNS = [
    r'\d+\s*%',
    r'\d+\s*prosentti',
    r'\bkasvu\b',
    r'\blasku\b',
    r'\bmuutos\b',
]

# Lukumäärät
COUNT_PATTERNS = [
    r'\d+\s*osallistujaa?',
    r'\d+\s*henkilöä?',
    r'\d+\s*nuorta\b',
    r'\d+\s*koulutusta\b',
    r'\d+\s*projektia\b',
    r'\bsatoja\b',
    r'\bkymmeniä\b',
    r'\btuhansia\b',
    r'\bmontako\b',
    r'\bkuinka monta\b',
]

# Relatiiviset ajat
RELATIVE_TIME_PATTERNS = [
    r'\bviime vuonna\b',
    r'\btänä vuonna\b',
    r'\bviime kaudella\b',
    r'\bviime kuussa\b',
    r'\btänä keväänä\b',
    r'\bviime syksynä\b',
    r'\bensi vuonna\b',
    r'\bäskettäin\b',
    r'\bhiljattain\b',
]

# Kysymyssanat
WHO_PATTERNS = [r'\bkuka\b', r'\bketkä\b', r'\bkenen\b']
HOW_MUCH_PATTERNS = [r'\bkuinka paljon\b', r'\bmontako\b', r'\bkuinka monta\b', r'\bpaljonko\b']
WHEN_PATTERNS = [r'\bmilloin\b', r'\bkoska\b', r'\bminä päivänä\b', r'\bminä vuonna\b']

# Viralliset vaatimukset (=> web_required)
OFFICIAL_PATTERNS = [
    r'\bstea.ohje',
    r'\bstea.vaatimus',
    r'\bstea.hakemus.*vaatimus',
    r'\bhakemus.*vaatimus',
    r'\berasmus\+?\s*(ohje|guide|vaatimus)',
    r'\bthl.suositus',
    r'\blaki\s*sanoo\b',
    r'\bvirallinen\b',
    r'\bvaatimukset\b',
    r'\bmääräys\b',
    r'\basetus\b',
    r'\bprogramme guide\b',
    r'\boph.*ohje',
]

# Henkilönimet - yksinkertainen heuristiikka (isot alkukirjaimet)
NAME_PATTERN = r'\b[A-ZÄÖÅ][a-zäöå]+\s+[A-ZÄÖÅ][a-zäöå]+\b'

# Organisaatiot
ORG_PATTERNS = [
    r'\bsamha\b',
    r'\bstea\b',
    r'\bthl\b',
    r'\boph\b',
    r'\bmieli\s*ry\b',
    r'\ba-klinikka\b',
    r'\bhallitus\b',
    r'\bpuheenjohtaja\b',
    r'\btoiminnanjohtaja\b',
]

# Projektikoodit
PROJECT_PATTERNS = [
    r'\bhanke\s*\d+\b',
    r'\bprojekti\s*\d+\b',
    r'\b[A-Z]{2,4}-\d{4,}\b',  # XX-12345 format
]


def _match_any(text: str, patterns: List[str]) -> bool:
    """Tarkista löytyykö mikään pattern tekstistä."""
    text_lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def detect_gate_signals(user_message: str) -> HardGateSignals:
    """
    Tunnista hard gate -signaalit käyttäjän viestistä.
    
    Args:
        user_message: Käyttäjän alkuperäinen viesti
        
    Returns:
        HardGateSignals jossa rag_required ja web_required laskettu
    """
    text = user_message.strip()
    
    signals = HardGateSignals(
        # Numeric/temporal
        contains_year=_match_any(text, YEAR_PATTERNS),
        contains_money=_match_any(text, MONEY_PATTERNS),
        contains_percentage=_match_any(text, PERCENTAGE_PATTERNS),
        contains_count=_match_any(text, COUNT_PATTERNS),
        contains_relative_time=_match_any(text, RELATIVE_TIME_PATTERNS),
        
        # Entities
        contains_person_name=bool(re.search(NAME_PATTERN, text)),
        contains_organization=_match_any(text, ORG_PATTERNS),
        contains_project_code=_match_any(text, PROJECT_PATTERNS),
        
        # Questions
        asks_who=_match_any(text, WHO_PATTERNS),
        asks_how_much=_match_any(text, HOW_MUCH_PATTERNS),
        asks_when=_match_any(text, WHEN_PATTERNS),
        asks_official_requirement=_match_any(text, OFFICIAL_PATTERNS),
    )
    
    # model_validator laskee rag_required ja web_required automaattisesti
    return signals


def enforce_gates(
    signals: HardGateSignals,
    rag_used: bool,
    web_used: bool,
    rag_results_count: int = 0,
    web_results_count: int = 0,
) -> GateDecision:
    """
    Tarkista täytettiinkö gate-vaatimukset.
    
    Args:
        signals: Tunnistetut signaalit
        rag_used: Käytettiinkö RAG-hakua
        web_used: Käytettiinkö web-hakua
        rag_results_count: RAG-hakutulosten määrä
        web_results_count: Web-hakutulosten määrä
        
    Returns:
        GateDecision joka kertoo täytettiinkö vaatimukset
    """
    violations = []
    
    # Tarkista RAG-vaatimus
    if signals.rag_required:
        if not rag_used:
            violations.append("RAG_NOT_CALLED: rag_required=True but rag_used=False")
        elif rag_results_count == 0:
            violations.append("RAG_NO_RESULTS: RAG called but returned 0 results")
    
    # Tarkista Web-vaatimus
    if signals.web_required:
        if not web_used:
            violations.append("WEB_NOT_CALLED: web_required=True but web_used=False")
        elif web_results_count == 0:
            violations.append("WEB_NO_RESULTS: Web called but returned 0 results")
    
    # Päätä decision
    if signals.rag_required and signals.web_required:
        decision = "both_required"
    elif signals.web_required:
        decision = "web_required"
    elif signals.rag_required:
        decision = "rag_required"
    else:
        decision = "no_gate"
    
    return GateDecision(
        signals=signals,
        decision=decision,
        gate_satisfied=len(violations) == 0,
        violations=violations,
    )


def get_fallback_response_for_gate_violation(violations: List[str]) -> str:
    """
    Jos gate rikotaan ja hakutuloksia ei ole, palauta turvallinen fallback.
    
    Säännön mukaan: jos hard gate laukeaa ja retrieval tuottaa 0 tulosta,
    vastaus saa sisältää vain (a) kysymyksen tarkentamisen tai (b) yleisluontoisen ohjeen.
    """
    if "RAG_NO_RESULTS" in str(violations) or "WEB_NO_RESULTS" in str(violations):
        return (
            "Valitettavasti en löytänyt tarkkaa tietoa tähän kysymykseen sisäisestä "
            "tietokannasta tai virallisista lähteistä. Voisitko tarkentaa kysymystäsi, "
            "tai kerro minulle mistä aiheesta haluaisit yleisempää tietoa?"
        )
    
    if "RAG_NOT_CALLED" in str(violations):
        return "INTERNAL_ERROR: RAG should have been called but wasn't. Please retry."
    
    if "WEB_NOT_CALLED" in str(violations):
        return "INTERNAL_ERROR: Web search should have been called but wasn't. Please retry."
    
    return ""


# =============================================================================
# COORDINATOR HELPER - Käytettäväksi Koordinaattorissa
# =============================================================================

def process_user_message_with_gates(
    user_message: str,
    search_samha_fn: callable,
    search_web_fn: Optional[callable] = None,
) -> Tuple[GateDecision, List, List]:
    """
    Käsittele käyttäjän viesti hard gate -logiikalla.
    
    Pakottaa RAG/Web-haun jos signaalit vaativat.
    
    Args:
        user_message: Käyttäjän viesti
        search_samha_fn: Funktio sisäiseen RAG-hakuun
        search_web_fn: Funktio web-hakuun (optional)
        
    Returns:
        (GateDecision, rag_results, web_results)
    """
    # 1. Tunnista signaalit
    signals = detect_gate_signals(user_message)
    
    rag_results = []
    web_results = []
    
    # 2. Pakota RAG jos vaaditaan
    if signals.rag_required:
        try:
            rag_results = search_samha_fn(user_message)
        except Exception as e:
            print(f"DEBUG: RAG search failed: {e}")
            rag_results = []
    
    # 3. Pakota Web jos vaaditaan
    if signals.web_required and search_web_fn:
        try:
            web_results = search_web_fn(user_message)
        except Exception as e:
            print(f"DEBUG: Web search failed: {e}")
            web_results = []
    
    # 4. Arvioi täytettiinkö gates
    decision = enforce_gates(
        signals=signals,
        rag_used=signals.rag_required,  # Pakotettiin jos vaadittiin
        web_used=signals.web_required and search_web_fn is not None,
        rag_results_count=len(rag_results),
        web_results_count=len(web_results),
    )
    
    return decision, rag_results, web_results


# =============================================================================
# TESTING / DEBUG
# =============================================================================

def test_gate_detection():
    """Testaa gate-tunnistusta esimerkkiviesteillä."""
    test_cases = [
        ("Kerro Samhasta", True, False),  # Org name triggers RAG - correct!
        ("Paljonko Samha sai Stea-avustusta 2024?", True, False),
        ("Kuka on hallituksen puheenjohtaja?", True, False),
        ("Montako nuorta osallistui koulutuksiin viime vuonna?", True, False),
        ("Mitkä ovat Stea-hakemuksen vaatimukset?", True, True),
        ("Mitä on masennus?", False, False),
        ("Kerro Erasmus+ programme guide -ohjeista", True, True),
        ("Moi!", False, False),  # Simple greeting
        ("Suunnittele koulutus antirasismista", False, False),  # Creative task
    ]
    
    print("Gate Detection Test Results:")
    print("-" * 60)
    for message, expected_rag, expected_web in test_cases:
        signals = detect_gate_signals(message)
        status = "✅" if (signals.rag_required == expected_rag and signals.web_required == expected_web) else "❌"
        print(f"{status} '{message[:40]}...'")
        print(f"   RAG: {signals.rag_required} (expected {expected_rag})")
        print(f"   Web: {signals.web_required} (expected {expected_web})")
        print()


if __name__ == "__main__":
    test_gate_detection()
