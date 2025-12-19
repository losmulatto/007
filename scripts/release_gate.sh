#!/bin/bash
# Samha Release Gate Script

set -e

MODE=$1 # pr or nightly
SUITE25="full_eval_25.json"
SUITE80="full_suite_80.json"

echo "============================================================"
echo "SAMHA RELEASE GATE: $MODE"
echo "============================================================"

# always run 25
echo "--- Running $SUITE25 (PR Gate) ---"
uv run python eval_comprehensive.py --suite $SUITE25

if [ "$MODE" == "nightly" ] || [ "$MODE" == "full" ]; then
    echo "--- Running $SUITE80 (Regression) ---"
    uv run python eval_comprehensive.py --suite $SUITE80
fi

echo "============================================================"
echo "✅ ALL GATES PASSED"
echo "============================================================"
