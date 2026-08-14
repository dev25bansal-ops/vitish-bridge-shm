#!/usr/bin/env bash
# Merge gate — run before every push/merge. The demo arc must NEVER break.
#   bash scripts/verify_gate.sh
# Fails (non-zero exit) if either gate does not pass cleanly.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== gate 1/7: full smoke test (backend end-to-end) =="
python backend/tests/smoke_test.py
echo
echo "== gate 2/7: Z24 stiffness physics overlay (D1-2) =="
python backend/tests/test_stiffness.py
echo
echo "== gate 3/7: condition card from crack index (D1-3) =="
python backend/tests/test_condition.py
echo
echo "== gate 4/7: LTBP Markov deterioration (D1-4) =="
python backend/tests/test_deterioration.py
echo
echo "== gate 5/7: demo-arc regression (GREEN -> AMBER -> RED, pinned) =="
python backend/tests/test_demo_arc.py
echo
echo "== gate 6/7: temperature normalization of f1 (D2-10) =="
python backend/tests/test_temperature.py
echo
echo "== gate 7/7: data-realism manifest + synthetic channel models (D1-5) =="
python backend/tests/test_manifest.py
echo
echo "== ALL GATES PASS =="
