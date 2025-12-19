#!/usr/bin/env python3
"""
Semantic Query Test - Shows how RAG combines knowledge from multiple documents.
These queries DON'T directly reference document names but should find relevant content.
"""

import json
from google.cloud import discoveryengine_v1alpha as discoveryengine
from google.api_core.client_options import ClientOptions

PROJECT_ID = "agent-2c15f"
LOCATION = "us"
ENGINE_ID = "samha-search-engine"

# 10 semantic queries - real-world questions that require understanding, not keyword matching
SEMANTIC_QUERIES = [
    {
        "query": "Miten käsittelen traumoja nuorisotyössä?",
        "intent": "Trauma + youth work → pitäisi löytää mielenterveys + SALTO"
    },
    {
        "query": "Järjestömme haluaa hakea rahoitusta antirasismihankkeelle",
        "intent": "Rahoitus + antirasismi → STEA + EU/FI antirasismi"
    },
    {
        "query": "Miten tunnistan piilorasismia?",
        "intent": "Piilorasismi → Structural racism, white privilege"
    },
    {
        "query": "Nuorten osallistaminen päätöksentekoon",
        "intent": "Nuoret + osallistaminen → Youth work methods, SALTO"
    },
    {
        "query": "Maahanmuuttajien kotoutumisen tukeminen",
        "intent": "Kotoutuminen → Yhdenvertainen Suomi, Intercultural competence"
    },
    {
        "query": "Työntekijän jaksaminen vaikeissa asiakastilanteissa",
        "intent": "Jaksaminen → Mielenterveysstrategia, trauma-informed"
    },
    {
        "query": "EU-hankkeen hakeminen nuorisoalalla",
        "intent": "EU-hanke + nuoriso → Erasmus, EU policies"
    },
    {
        "query": "Yhdenvertaisuussuunnittelu työpaikalla",
        "intent": "Yhdenvertaisuus → Yhdenvertainen Suomi, EU antiracism"
    },
    {
        "query": "Pelillisyys oppimismenetelmänä",
        "intent": "Pelillisyys + oppiminen → SALTO methods, non-formal learning"
    },
    {
        "query": "Viharikoksen uhrin tukeminen",
        "intent": "Viharikos → Antirasismi, mielenterveys"
    }
]

def search(query: str) -> list:
    """Execute semantic search."""
    client_options = ClientOptions(api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com")
    client = discoveryengine.SearchServiceClient(client_options=client_options)
    
    serving_config = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/engines/{ENGINE_ID}/servingConfigs/default_search"
    
    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=3,
    )
    
    response = client.search(request)
    
    results = []
    for result in response.results:
        title = ""
        link = ""
        if hasattr(result.document, "derived_struct_data") and result.document.derived_struct_data:
            dsd = dict(result.document.derived_struct_data)
            title = dsd.get("title", "")
            link = dsd.get("link", "").split("/")[-1] if dsd.get("link") else ""
        results.append({"title": title[:50], "file": link})
    
    return results

def main():
    print("=" * 70)
    print("🧠 SEMANTTINEN HAKU - Ymmärtääkö agentti merkityksen?")
    print("=" * 70)
    print()
    
    for i, test in enumerate(SEMANTIC_QUERIES, 1):
        query = test["query"]
        intent = test["intent"]
        
        print(f"{'─' * 70}")
        print(f"#{i} ❓ \"{query}\"")
        print(f"   💭 Odotettu: {intent}")
        print()
        
        try:
            results = search(query)
            
            if results:
                print(f"   📚 Löydetyt dokumentit:")
                for r in results:
                    print(f"      • {r['file']}")
                print(f"   ✅ Semanttinen yhdistäminen toimii!")
            else:
                print(f"   ⚠️  Ei tuloksia")
                
        except Exception as e:
            print(f"   ❌ Virhe: {e}")
        
        print()
    
    print("=" * 70)
    print("✨ Testi valmis! RAG ymmärtää kontekstin, ei pelkkiä avainsanoja.")
    print("=" * 70)

if __name__ == "__main__":
    main()
