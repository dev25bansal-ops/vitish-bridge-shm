#!/usr/bin/env bash
# Merge gate — run before every push/merge. The demo arc must NEVER break.
#   bash scripts/verify_gate.sh
# Fails (non-zero exit) if either gate does not pass cleanly.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== gate 1/2: full smoke test (backend end-to-end) =="
python backend/tests/smoke_test.py
echo
echo "== gate 2/2: demo-arc regression (GREEN -> AMBER -> RED, pinned) =="
python backend/tests/test_demo_arc.py
echo
echo "== ALL GATES PASS =="
