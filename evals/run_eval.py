#!/usr/bin/env python
"""
Samha Multi-Agent Eval Runner

Ajaa eval-testit ja tuottaa tulokset scorer.py:lle.

Käyttö:
  uv run python evals/run_eval.py --suite golden_25
  uv run python evals/run_eval.py --suite golden_25 --category routing_intent
  uv run python evals/run_eval.py --suite golden_25 --quick  # vain 5 ensimmäistä
"""

import os
import sys
import json
import time
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)


def load_suite(suite_name: str) -> dict:
    """Load eval suite JSON."""
    suite_path = Path(__file__).parent / f"{suite_name}.json"
    if not suite_path.exists():
        raise FileNotFoundError(f"Suite not found: {suite_path}")
    
    with open(suite_path, "r", encoding="utf-8") as f:
        return json.load(f)


async def run_single_case(
    runner,
    session_service,
    case: dict,
    case_index: int,
    total_cases: int
) -> dict:
    """Run a single eval case and return result."""
    from google.genai import types as genai_types
    
    case_id = case.get("id", f"case_{case_index}")
    user_input = case.get("user_input", "")
    
    print(f"  [{case_index+1}/{total_cases}] {case_id}...", end="", flush=True)
    
    start_time = time.time()
    response_text = ""
    agents_used = []
    tool_calls = []
    rag_used = False
    web_used = False
    error = None
    
    try:
        # Create session
        session = await session_service.create_session(
            app_name="samha_eval",
            user_id="eval_user",
        )
        
        # Create user message
        user_content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_input)]
        )
        
        # Run agent
        async for event in runner.run_async(
            session_id=session.id,
            user_id="eval_user",
            new_message=user_content,
        ):
            # Extract response text
            if hasattr(event, 'content') and event.content:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        response_text += part.text
            
            # Track agent used
            if hasattr(event, 'author') and event.author:
                if event.author not in agents_used:
                    agents_used.append(event.author)
            
            # Track tool calls (simplified - look for patterns in response)
            # Full implementation would track actual tool events
    
    except Exception as e:
        error = str(e)
        print(f" ❌ ERROR", end="")
    
    elapsed_ms = int((time.time() - start_time) * 1000)
    
    # Detect tool usage from response text
    response_lower = response_text.lower()
    if "context provided" in response_lower or "document" in response_lower:
        rag_used = True
        tool_calls.append("retrieve_docs")
    if "url:" in response_lower or "http" in response_lower:
        web_used = True
        if "stea.fi" in response_lower or "thl.fi" in response_lower:
            tool_calls.append("search_verified_sources")
        else:
            tool_calls.append("search_web")
    
    # Determine pass/fail (simplified)
    passed = error is None and len(response_text) > 50
    
    if passed:
        print(f" ✅ ({elapsed_ms}ms)")
    else:
        print(f" ❌ ({elapsed_ms}ms)")
    
    return {
        "id": case_id,
        "agents_used": agents_used,
        "tool_calls": tool_calls,
        "rag_used": rag_used,
        "web_used": web_used,
        "response_text": response_text[:5000],  # Truncate for storage
        "response_time_ms": elapsed_ms,
        "error": error
    }


async def run_eval_async(
    suite: dict,
    category: Optional[str] = None,
    quick: bool = False,
    max_cases: Optional[int] = None
) -> dict:
    """Run evaluation asynchronously."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from app.agent import koordinaattori_agent
    
    # Initialize runner
    session_service = InMemorySessionService()
    runner = Runner(
        agent=koordinaattori_agent,
        app_name="samha_eval",
        session_service=session_service,
    )
    
    # Filter cases
    cases = suite.get("cases", [])
    if category:
        cases = [c for c in cases if c.get("category") == category]
    if quick:
        cases = cases[:5]
    if max_cases:
        cases = cases[:max_cases]
    
    print(f"\n{'='*60}")
    print(f"SAMHA EVAL RUNNER - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"Suite: {suite.get('suite_name', 'unknown')}")
    print(f"Cases: {len(cases)}")
    if category:
        print(f"Category filter: {category}")
    print()
    
    results = []
    for i, case in enumerate(cases):
        result = await run_single_case(runner, session_service, case, i, len(cases))
        results.append(result)
    
    return {
        "run_id": f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "suite_name": suite.get("suite_name", "unknown"),
        "timestamp": datetime.now().isoformat(),
        "total_cases": len(cases),
        "results": results
    }


def run_eval(
    suite: dict,
    category: Optional[str] = None,
    quick: bool = False,
    max_cases: Optional[int] = None
) -> dict:
    """Run evaluation synchronously."""
    return asyncio.run(run_eval_async(suite, category, quick, max_cases))


def main():
    parser = argparse.ArgumentParser(description="Samha Multi-Agent Eval Runner")
    parser.add_argument("--suite", default="golden_25", help="Eval suite name (without .json)")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--quick", action="store_true", help="Run only first 5 cases")
    parser.add_argument("--max", type=int, help="Maximum number of cases to run")
    parser.add_argument("--output", default="run_results.json", help="Output file path")
    args = parser.parse_args()
    
    # Load suite
    try:
        suite = load_suite(args.suite)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Run eval
    results = run_eval(
        suite,
        category=args.category,
        quick=args.quick,
        max_cases=args.max
    )
    
    # Save results
    output_path = Path(__file__).parent / args.output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 Results saved to: {output_path}")
    
    # Print summary
    passed = sum(1 for r in results["results"] if r.get("error") is None and len(r.get("response_text", "")) > 50)
    failed = len(results["results"]) - passed
    
    print(f"\n{'='*60}")
    print(f"QUICK SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Ran successfully: {passed}/{results['total_cases']}")
    print(f"❌ Errors: {failed}/{results['total_cases']}")
    
    # Suggest running scorer
    print(f"\n💡 To score results, run:")
    print(f"   uv run python evals/scorer.py evals/{args.suite}.json {output_path}")


if __name__ == "__main__":
    main()
