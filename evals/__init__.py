"""
Samha Multi-Agent Evaluation Package

Käyttö:
  uv run python -m evals.run_eval --suite golden_25 --quick
  uv run python -m evals.scorer evals/golden_25.json run_results.json
"""

from .scorer import Scorer, ScoreResult
from .run_eval import run_eval, load_suite

__all__ = ["Scorer", "ScoreResult", "run_eval", "load_suite"]
