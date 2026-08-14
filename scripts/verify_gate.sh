#!/usr/bin/env bash
# Merge gate — run before every push/merge. The demo arc must NEVER break.
#   bash scripts/verify_gate.sh
# Fails (non-zero exit) if either gate does not pass cleanly.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== gate 1/5: full smoke test (backend end-to-end) =="
python backend/tests/smoke_test.py
echo
echo "== gate 2/5: Z24 stiffness physics overlay (D1-2) =="
python backend/tests/test_stiffness.py
echo
echo "== gate 3/5: condition card from crack index (D1-3) =="
python backend/tests/test_condition.py
echo
echo "== gate 4/5: LTBP Markov deterioration (D1-4) =="
python backend/tests/test_deterioration.py
echo
echo "== gate 5/5: demo-arc regression (GREEN -> AMBER -> RED, pinned) =="
python backend/tests/test_demo_arc.py
echo
echo "== ALL GATES PASS =="
