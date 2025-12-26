import os

CONTRACTS_DIR = os.path.join(os.path.dirname(__file__), "contracts")

def load_contract(agent_type: str) -> str:
    """
    Loads the contract markdown for a specific agent type.
    """
    map_filename = {
        "kirjoittaja": "kirjoittaja.md",
        "koulutus": "koulutus.md",
        "viestinta": "viestinta.md",
        "tutkija": "tutkija.md",
        "talous": "talous.md",
        "sote": "sote.md",
        "yhdenvertaisuus": "yhdenvertaisuus.md",
        "arkisto": "arkisto.md",
        "proposal_reviewer": "proposal_reviewer.md",
        "syvahaku": "syvahaku.md",
        "hankesuunnittelija": "hankesuunnittelija.md",
        "hallinto": "hallinto.md",
        "hr": "hr.md",
        "laki_gdpr": "laki_gdpr.md",
        "vapaaehtoiset": "vapaaehtoiset.md",
        "lomakkeet": "lomakkeet.md",
        "kumppanit": "kumppanit.md",
        "qa_policy": "qa_policy.md",
        "qa_quality": "qa_quality.md",
        "grant_writer": "grant_writer.md"
    }
    
    filename = map_filename.get(agent_type)
    if not filename:
        return ""
        
    path = os.path.join(CONTRACTS_DIR, filename)
    if not os.path.exists(path):
        return f"[ERROR: Contract {filename} not found]"
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"[ERROR loading contract: {e}]"
