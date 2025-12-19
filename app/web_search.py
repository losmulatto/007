"""
Samha Web Search Tool

Kaksi hakumoodia:
1. `verified` - Luotettavat lähteet (stea.fi, thl.fi, oph.fi, finlex.fi)
2. `general` - Laaja haku uutisiin ja ajankohtaisiin

Käyttää Google Custom Search API:ta.

Asennus:
1. Luo Google Custom Search Engine: https://programmablesearchengine.google.com/
2. Hae API Key: https://console.cloud.google.com/apis/credentials
3. Aseta .env:
   GOOGLE_SEARCH_API_KEY=xxx
   GOOGLE_SEARCH_ENGINE_ID=xxx  (general search)
   GOOGLE_SEARCH_ENGINE_ID_VERIFIED=xxx  (verified sources only)
"""

import os
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
import httpx

# Load .env file if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback: load .env manually if dotenv not installed
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key, value)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Verified sources (prioritized, trusted) - KATTAVA LISTA
VERIFIED_DOMAINS = [
    # --- RAHOITTAJAT ---
    "stea.fi",              # Stea - päärahoittaja
    "erasmus-plus.ec.europa.eu",  # Erasmus+
    "oph.fi",               # OPH - Erasmus+ kansallinen
    "eura2021.fi",          # EU-rahoitus
    "businessfinland.fi",   # Innovaatiorahoitus
    
    # --- VIRANOMAISET ---
    "stm.fi",               # Sosiaali- ja terveysministeriö
    "tem.fi",               # Työ- ja elinkeinoministeriö
    "okm.fi",               # Opetus- ja kulttuuriministeriö
    "valtioneuvosto.fi",    # Valtioneuvosto
    "eduskunta.fi",         # Eduskunta
    "finlex.fi",            # Lainsäädäntö
    
    # --- TERVEYSTIETO ---
    "thl.fi",               # THL - tilastot, tutkimus
    "mielenterveystalo.fi", # Mielenterveystalo
    "kaypahoito.fi",        # Käypä hoito -suositukset
    "terveyskirjasto.fi",   # Terveyskirjasto (Duodecim)
    "fimea.fi",             # Lääkevirasto
    
    # --- JÄRJESTÖT (SOTE) ---
    "mieli.fi",             # Mieli ry - mielenterveys
    "ehyt.fi",              # Ehyt ry - päihdetyö
    "a-klinikka.fi",        # A-klinikka
    "a-klinikkasaatio.fi",  # A-klinikkasäätiö
    "paihdelinkki.fi",      # Päihdelinkki
    "yeesi.fi",             # Yeesi ry - nuoret
    "mll.fi",               # Mannerheimin lastensuojeluliitto
    "pelastakaalapset.fi",  # Pelastakaa Lapset
    "punainenristi.fi",     # Punainen Risti
    "soste.fi",             # SOSTE ry
    
    # --- JÄRJESTÖT (YHDENVERTAISUUS) ---
    "syrjinta.fi",          # Yhdenvertaisuusvaltuutettu
    "yhdenvertaisuus.fi",   # Yhdenvertaisuus
    "moniheli.fi",          # Moniheli - maahanmuuttajat
    "pakolaisapu.fi",       # Pakolaisapu
    "ihmisoikeuskeskus.fi", # Ihmisoikeuskeskus
    "ihmisoikeusliitto.fi", # Ihmisoikeusliitto
    "unicef.fi",            # UNICEF
    
    # --- KOULUTUS & NUORISOTYÖ ---
    "nuorisotutkimusseura.fi",  # Nuorisotutkimusseura
    "allianssi.fi",         # Nuorisotyön keskusliitto
    "kansalaisareena.fi",   # Kansalaisareena
    
    # --- KUNTASEKTORI ---
    "kuntaliitto.fi",       # Kuntaliitto
    "hel.fi",               # Helsinki
    "espoo.fi",             # Espoo
    "vantaa.fi",            # Vantaa
    "oulu.fi",              # Oulu
    "tampere.fi",           # Tampere
    
    # --- TUTKIMUS ---
    "julkari.fi",           # Julkaisut (THL, STM)
    "stat.fi",              # Tilastokeskus
    "sotkanet.fi",          # Sotkanet (THL tilastot)
    "aka.fi",               # Suomen Akatemia
    
    # --- KELA & PALVELUT ---
    "kela.fi",              # Kela
    "te-palvelut.fi",       # TE-palvelut
    "tyosuojelu.fi",        # Työsuojelu
    "vero.fi",              # Verohallinto
    "prh.fi",               # PRH - yhdistysrekisteri
    
    # --- EUROOPPA ---
    "ec.europa.eu",         # EU Commission
    "salto-youth.net",      # SALTO-YOUTH
    "youthpass.eu",         # Youthpass
    "otlas.eu",             # OTLAS partnerhaku
]

# News sources for general search (Finnish media)
NEWS_DOMAINS = [
    "yle.fi",               # Yle - luotettavin
    "hs.fi",                # Helsingin Sanomat
    "mtv.fi",               # MTV Uutiset
    "is.fi",                # Ilta-Sanomat
    "iltalehti.fi",         # Iltalehti
    "maaseuduntulevaisuus.fi",  # Maaseudun Tulevaisuus
    "kauppalehti.fi",       # Kauppalehti
    "talouselama.fi",       # Talouselämä
    "mediuutiset.fi",       # Medi-uutiset (sote)
    "sosiaalitieto.fi",     # Sosiaalitieto
]

# International sources for Erasmus+ etc
INTERNATIONAL_DOMAINS = [
    # --- EU & ERASMUS+ ---
    "erasmus-plus.ec.europa.eu",
    "ec.europa.eu",
    "salto-youth.net",
    "youthpass.eu",
    "otlas.eu",
    "coe.int",              # Council of Europe
    
    # --- MENTAL HEALTH (English) ---
    "who.int",              # WHO - mental health
    "mentalhealth.org.uk",  # Mental Health Foundation UK
    "mind.org.uk",          # Mind UK
    "nimh.nih.gov",         # NIH Mental Health (USA)
    "samhsa.gov",           # SAMHSA (USA)
    "beyondblue.org.au",    # Beyond Blue (Australia)
    "camh.ca",              # CAMH (Canada)
    "psychiatry.org",       # APA
    "apa.org",              # American Psychological Assoc
    
    # --- SUBSTANCE ABUSE (English) ---
    "drugabuse.gov",        # NIDA (USA)
    "emcdda.europa.eu",     # EU Drug Agency
    "harmreduction.org",    # Harm Reduction International
    "unodc.org",            # UNODC
    "transformdrugs.org",   # Transform Drug Policy
    
    # --- MIGRATION & REFUGEES ---
    "unhcr.org",            # UNHCR
    "iom.int",              # IOM
    "migrationpolicy.org",  # Migration Policy Institute
    "oecd.org",             # OECD (migration)
    "refugeecouncil.org.uk",# Refugee Council UK
    "ecre.org",             # European Council on Refugees
    
    # --- ANTI-RACISM & EQUALITY ---
    "enar-eu.org",          # European Network Against Racism
    "theguardian.com",      # Guardian (Race section)
    "amnesty.org",          # Amnesty International
    "humanrightsfirst.org", # Human Rights First
    "splcenter.org",        # Southern Poverty Law Center
    "adl.org",              # Anti-Defamation League
    
    # --- YOUTH WORK ---
    "youth.europa.eu",      # European Youth Portal
    "pjp-eu.coe.int",       # Youth Partnership COE-EU
    "ncbi.nlm.nih.gov",     # PubMed (research)
    "researchgate.net",     # Research articles
    "scholar.google.com",   # Google Scholar
    
    # --- NORDIC RESEARCH ---
    "norden.org",           # Nordic Council
    "nordforsk.org",        # NordForsk research
    "nordicwelfare.org",    # Nordic Welfare Centre
    "nikk.no",              # Nordic Gender Institute
]

# Academic/Research sources (always considered verified)
RESEARCH_DOMAINS = [
    "ncbi.nlm.nih.gov",     # PubMed / NCBI
    "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com",   # Google Scholar
    "researchgate.net",     # ResearchGate
    "academia.edu",         # Academia.edu
    "jstor.org",            # JSTOR
    "sciencedirect.com",    # ScienceDirect
    "springer.com",         # Springer
    "wiley.com",            # Wiley
    "tandfonline.com",      # Taylor & Francis
    "bmj.com",              # BMJ
    "thelancet.com",        # The Lancet
    "nature.com",           # Nature
    "frontiersin.org",      # Frontiers
    "mdpi.com",             # MDPI journals
    "oecd-ilibrary.org",    # OECD iLibrary
]


# =============================================================================
# MODELS
# =============================================================================

SearchMode = Literal["verified", "general", "news"]


class WebSearchResult(BaseModel):
    """Yksittäinen hakutulos."""
    
    title: str = Field(..., description="Sivun otsikko")
    url: str = Field(..., description="URL")
    snippet: str = Field(..., description="Ote sisällöstä")
    domain: str = Field(..., description="Domain (esim. stea.fi)")
    is_verified: bool = Field(False, description="Onko luotettu lähde")
    date: Optional[str] = Field(None, description="Päivämäärä jos saatavilla")
    
    @property
    def source_label(self) -> str:
        return "✅ Luotettu" if self.is_verified else "🔍 Haku"


class WebSearchResponse(BaseModel):
    """Hakuvastaus."""
    
    query: str
    mode: SearchMode
    results: List[WebSearchResult]
    total_found: int
    search_time_ms: int


# =============================================================================
# SEARCH SERVICE
# =============================================================================

class WebSearchService:
    """
    Google Custom Search API wrapper.
    
    Tukee kahta Search Engine ID:tä:
    - GOOGLE_SEARCH_ENGINE_ID: Yleinen haku
    - GOOGLE_SEARCH_ENGINE_ID_VERIFIED: Vain luotetut lähteet
    """
    
    def __init__(self):
        self.api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
        self.engine_id = os.environ.get("GOOGLE_SEARCH_ENGINE_ID")
        self.engine_id_verified = os.environ.get("GOOGLE_SEARCH_ENGINE_ID_VERIFIED")
        
        if not self.api_key:
            print("WARNING: GOOGLE_SEARCH_API_KEY not set, web search disabled")
        if not self.engine_id:
            print("WARNING: GOOGLE_SEARCH_ENGINE_ID not set")
    
    def _is_verified_domain(self, url: str) -> bool:
        """Check if URL is from verified source."""
        for domain in VERIFIED_DOMAINS + INTERNATIONAL_DOMAINS + RESEARCH_DOMAINS:
            if domain in url:
                return True
        return False
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return url
    
    async def search_async(
        self,
        query: str,
        mode: SearchMode = "general",
        num_results: int = 10,
        date_restrict: Optional[str] = None,  # e.g., "m1" = last month
    ) -> WebSearchResponse:
        """
        Async web search.
        
        Args:
            query: Hakusana
            mode: "verified" | "general" | "news"
            num_results: Tulosten määrä (max 10)
            date_restrict: Aikarajaus (d=day, w=week, m=month, y=year)
        """
        import time
        start_time = time.time()
        
        if not self.api_key:
            return WebSearchResponse(
                query=query,
                mode=mode,
                results=[],
                total_found=0,
                search_time_ms=0
            )
        
        # Choose engine based on mode
        if mode == "verified" and self.engine_id_verified:
            engine = self.engine_id_verified
        else:
            engine = self.engine_id
        
        # Build search query
        search_query = query
        if mode == "news":
            # Add news-specific terms
            search_query = f"{query} uutiset ajankohtaista"
        elif mode == "verified":
            # Add site: restrictions for verified domains
            site_query = " OR ".join([f"site:{d}" for d in VERIFIED_DOMAINS[:5]])
            search_query = f"{query} ({site_query})"
        
        # Make API request
        params = {
            "key": self.api_key,
            "cx": engine,
            "q": search_query,
            "num": min(num_results, 10),
            "lr": "lang_fi",  # Finnish language
        }
        
        if date_restrict:
            params["dateRestrict"] = date_restrict
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            print(f"Web search error: {e}")
            return WebSearchResponse(
                query=query,
                mode=mode,
                results=[],
                total_found=0,
                search_time_ms=int((time.time() - start_time) * 1000)
            )
        
        # Parse results
        results = []
        items = data.get("items", [])
        
        for item in items:
            url = item.get("link", "")
            results.append(WebSearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=item.get("snippet", ""),
                domain=self._extract_domain(url),
                is_verified=self._is_verified_domain(url),
                date=item.get("pagemap", {}).get("metatags", [{}])[0].get("article:published_time")
            ))
        
        # Sort verified first
        results.sort(key=lambda r: (not r.is_verified, r.title))
        
        total = int(data.get("searchInformation", {}).get("totalResults", 0))
        
        return WebSearchResponse(
            query=query,
            mode=mode,
            results=results,
            total_found=total,
            search_time_ms=int((time.time() - start_time) * 1000)
        )
    
    def search(
        self,
        query: str,
        mode: SearchMode = "general",
        num_results: int = 10,
        date_restrict: Optional[str] = None,
    ) -> WebSearchResponse:
        """Synchronous web search - works in ADK context."""
        import time
        import requests
        
        start_time = time.time()
        
        if not self.api_key:
            return WebSearchResponse(
                query=query,
                mode=mode,
                results=[],
                total_found=0,
                search_time_ms=0
            )
        
        # Choose engine based on mode
        if mode == "verified" and self.engine_id_verified:
            engine = self.engine_id_verified
        else:
            engine = self.engine_id
        
        if not engine:
            return WebSearchResponse(
                query=query,
                mode=mode,
                results=[],
                total_found=0,
                search_time_ms=0
            )
        
        # Build search query
        search_query = query
        if mode == "news":
            search_query = f"{query} uutiset ajankohtaista"
        elif mode == "verified":
            site_query = " OR ".join([f"site:{d}" for d in VERIFIED_DOMAINS[:5]])
            search_query = f"{query} ({site_query})"
        
        # Make API request (synchronous)
        params = {
            "key": self.api_key,
            "cx": engine,
            "q": search_query,
            "num": min(num_results, 10),
            "lr": "lang_fi",
        }
        
        if date_restrict:
            params["dateRestrict"] = date_restrict
        
        try:
            response = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params,
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"Web search error: {e}")
            return WebSearchResponse(
                query=query,
                mode=mode,
                results=[],
                total_found=0,
                search_time_ms=int((time.time() - start_time) * 1000)
            )
        
        # Parse results
        results = []
        items = data.get("items", [])
        
        for item in items:
            url = item.get("link", "")
            results.append(WebSearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=item.get("snippet", ""),
                domain=self._extract_domain(url),
                is_verified=self._is_verified_domain(url),
                date=item.get("pagemap", {}).get("metatags", [{}])[0].get("article:published_time") if item.get("pagemap") else None
            ))
        
        # Sort verified first
        results.sort(key=lambda r: (not r.is_verified, r.title))
        
        total = int(data.get("searchInformation", {}).get("totalResults", 0))
        
        return WebSearchResponse(
            query=query,
            mode=mode,
            results=results,
            total_found=total,
            search_time_ms=int((time.time() - start_time) * 1000)
        )


# =============================================================================
# TOOL FUNCTIONS (for agents)
# =============================================================================

_web_search_service: Optional[WebSearchService] = None

def get_web_search_service() -> WebSearchService:
    global _web_search_service
    if _web_search_service is None:
        _web_search_service = WebSearchService()
    return _web_search_service


def search_web(
    query: str,
    mode: str = "general",
    max_results: int = 10,
    time_range: str = "",
) -> str:
    """
    Hae tietoa verkosta. Käytä tätä kun tarvitset:
    - Ajankohtaisia uutisia ja tapahtumia
    - Virallisia ohjeita (Stea, THL, OPH)
    - Ulkoista tietoa joka ei ole Samhan tietokannassa
    
    Args:
        query: Hakusana suomeksi
        mode: Hakumoodi
            - "verified": Vain luotetut lähteet (stea.fi, thl.fi, oph.fi)
            - "general": Laaja haku kaikista lähteistä
            - "news": Uutiset ja ajankohtaiset
        max_results: Tulosten maksimimäärä (1-10)
        time_range: Aikarajaus
            - "": Ei rajausta
            - "d7": Viimeiset 7 päivää
            - "m1": Viimeinen kuukausi
            - "m3": Viimeiset 3 kuukautta
            - "y1": Viimeinen vuosi
    
    Returns:
        Hakutulokset muotoiltuna tekstinä
    """
    service = get_web_search_service()
    
    # Map time_range to Google format
    date_restrict = None
    if time_range:
        date_restrict = time_range
    
    try:
        response = service.search(
            query=query,
            mode=mode,  # type: ignore
            num_results=min(max_results, 10),
            date_restrict=date_restrict
        )
    except Exception as e:
        return f"Hakuvirhe: {e}"
    
    if not response.results:
        return f"Ei tuloksia haulle: '{query}' (moodi: {mode})"
    
    # Format output with FULL URLs clearly visible
    output = f"## Web-haku: {query}\n"
    output += f"Moodi: {mode} | Tuloksia: {len(response.results)}/{response.total_found}\n\n"
    
    for i, result in enumerate(response.results, 1):
        label = result.source_label
        output += f"### {i}. {result.title}\n"
        output += f"**URL:** {result.url}\n"
        output += f"**Lähde:** {result.domain} {label}\n"
        output += f"**Sisältö:** {result.snippet}\n\n"
    
    return output


def search_verified_sources(query: str, max_results: int = 10) -> str:
    """
    Hae VAIN luotetuista lähteistä (stea.fi, thl.fi, oph.fi, finlex.fi).
    Käytä tätä kun tarvitset virallisia ohjeita tai säädöksiä.
    
    Args:
        query: Hakusana suomeksi
        max_results: Tulosten määrä
    
    Returns:
        Hakutulokset vain luotetuista lähteistä
    """
    return search_web(query, mode="verified", max_results=max_results)


def search_news(query: str, time_range: str = "m1", max_results: int = 10) -> str:
    """
    Hae ajankohtaisia uutisia ja artikkeleita.
    Käytä tätä kun haluat kirjoittaa ajankohtaisista aiheista.
    
    Args:
        query: Hakusana suomeksi
        time_range: Aikarajaus (d7=viikko, m1=kuukausi, m3=3kk, y1=vuosi)
        max_results: Tulosten määrä
    
    Returns:
        Uutiset ja ajankohtaiset
    """
    return search_web(query, mode="news", max_results=max_results, time_range=time_range)


# =============================================================================
# FALLBACK: Vertex AI Search (if Google Custom Search not configured)
# =============================================================================

def search_web_fallback(query: str) -> str:
    """
    Fallback web search using grounding (if Custom Search not configured).
    Uses Gemini's built-in web access.
    """
    # This would use Gemini's grounding feature
    # For now, return a helpful message
    return f"""
Web-haku ei ole konfiguroitu. Aseta .env:
- GOOGLE_SEARCH_API_KEY
- GOOGLE_SEARCH_ENGINE_ID

Voit myös käyttää Geminin sisäänrakennettua web-hakua käyttämällä
`google_search` -työkalua ADK:ssa.

Hakusana oli: {query}
"""


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    # Test
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
    if api_key:
        print(search_web("Stea avustukset 2025", mode="verified"))
        print("---")
        print(search_news("mielenterveys nuoret", time_range="m1"))
    else:
        print("GOOGLE_SEARCH_API_KEY not set, skipping test")
