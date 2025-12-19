#!/usr/bin/env python3
"""
RAG Knowledge Base Test Script
Tests the Samha Knowledge Base for document retrieval quality.
"""

import os
import json
from google.cloud import discoveryengine_v1alpha as discoveryengine

PROJECT_ID = "agent-2c15f"
LOCATION = "us"
ENGINE_ID = "samha-search-engine"
DATASTORE_ID = "samha-knowledge-base"

# Test queries covering all document categories
TEST_QUERIES = [
    # STEA documents
    {
        "query": "STEA avustuksen hakeminen",
        "expected_docs": ["avustusopas"],
        "category": "STEA"
    },
    {
        "query": "avustuksen käyttö ja raportointi",
        "expected_docs": ["avustusopas"],
        "category": "STEA"
    },
    # SOTE/Youth Work
    {
        "query": "mielenterveysstrategia",
        "expected_docs": ["mielenterveysstrategia"],
        "category": "SOTE"
    },
    {
        "query": "youth work methods non-formal learning",
        "expected_docs": ["salto", "methods"],
        "category": "Youth Work"
    },
    # Anti-racism
    {
        "query": "structural racism institutional racism",
        "expected_docs": ["structural_racism", "racism"],
        "category": "Anti-racism"
    },
    {
        "query": "white privilege McIntosh",
        "expected_docs": ["mcintosh", "privilege"],
        "category": "Anti-racism"
    },
    {
        "query": "EU anti-racism action plan",
        "expected_docs": ["eu_antiracism", "action_plan"],
        "category": "Anti-racism"
    },
    {
        "query": "yhdenvertainen suomi",
        "expected_docs": ["yhdenvertainen"],
        "category": "Anti-racism (FI)"
    },
    {
        "query": "intercultural competence training",
        "expected_docs": ["coe_intercultural", "competence"],
        "category": "Anti-racism"
    },
]

def search_datastore(query: str, page_size: int = 5) -> list:
    """Execute a search query against the datastore."""
    from google.api_core.client_options import ClientOptions
    
    # Use regional endpoint for US location
    client_options = ClientOptions(
        api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com"
    )
    client = discoveryengine.SearchServiceClient(client_options=client_options)
    
    serving_config = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/engines/{ENGINE_ID}/servingConfigs/default_search"
    
    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=page_size,
    )
    
    response = client.search(request)
    
    results = []
    for result in response.results:
        doc_data = {
            "id": result.document.id,
            "title": "",
            "link": ""
        }
        
        if hasattr(result.document, "derived_struct_data") and result.document.derived_struct_data:
            dsd = dict(result.document.derived_struct_data)
            doc_data["title"] = dsd.get("title", "")
            doc_data["link"] = dsd.get("link", "")
        
        results.append(doc_data)
    
    return results

def run_tests():
    """Run all test queries and report results."""
    print("=" * 60)
    print("🔍 RAG Knowledge Base Test Suite")
    print("=" * 60)
    print(f"Datastore: {DATASTORE_ID}")
    print(f"Engine: {ENGINE_ID}")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test in TEST_QUERIES:
        query = test["query"]
        expected = test["expected_docs"]
        category = test["category"]
        
        print(f"\n📋 [{category}] Query: '{query}'")
        print("-" * 50)
        
        try:
            results = search_datastore(query)
            
            if not results:
                print("   ❌ No results found")
                failed += 1
                continue
            
            # Check if any expected doc is in results
            found_expected = False
            for result in results[:3]:  # Check top 3
                title = result.get("title", "").lower()
                link = result.get("link", "").lower()
                combined = title + " " + link
                
                for exp in expected:
                    if exp.lower() in combined:
                        found_expected = True
                        break
                
                print(f"   📄 {title or 'Untitled'}")
                print(f"      {link}")
            
            if found_expected:
                print("   ✅ PASS - Expected document found")
                passed += 1
            else:
                print("   ⚠️  PARTIAL - Results found but not expected docs")
                passed += 0.5
                failed += 0.5
                
        except Exception as e:
            print(f"   ❌ ERROR: {type(e).__name__}: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 RESULTS: {passed}/{len(TEST_QUERIES)} passed")
    print("=" * 60)
    
    return passed, failed

if __name__ == "__main__":
    run_tests()
