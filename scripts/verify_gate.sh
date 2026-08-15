#!/usr/bin/env bash
# Merge gate — run before every push/merge. The demo arc must NEVER break.
#   bash scripts/verify_gate.sh
# Fails (non-zero exit) if any gate does not pass cleanly.
# Superset: scripts/run_tests.sh runs every standalone test file (14 backend
# tests + scripts/verify_demo_arc.py) in one command — CI uses that runner.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== gate 1/15: full smoke test (backend end-to-end) =="
python backend/tests/smoke_test.py
echo
echo "== gate 2/15: Z24 stiffness physics overlay (D1-2) =="
python backend/tests/test_stiffness.py
echo
echo "== gate 3/15: condition card from crack index (D1-3) =="
python backend/tests/test_condition.py
echo
echo "== gate 4/15: LTBP Markov deterioration (D1-4) =="
python backend/tests/test_deterioration.py
echo
echo "== gate 5/15: demo-arc regression (GREEN -> AMBER -> RED, pinned) =="
python backend/tests/test_demo_arc.py
echo
echo "== gate 6/15: temperature normalization of f1 (D2-10) =="
python backend/tests/test_temperature.py
echo
echo "== gate 7/15: data-realism manifest + synthetic channel models (D1-5) =="
python backend/tests/test_manifest.py
echo
echo "== gate 8/15: seeded-defect demo grounded in Z24/S101 (D2-12) =="
python backend/tests/test_seeded_defect.py
echo
echo "== gate 9/15: newer HTTP routes (live/manifest/stiffness/seeded-defect/deterioration/condition/config) =="
python backend/tests/test_api_routes.py
echo
echo "== gate 10/15: trained-path regression (shipped artifacts, relabeled inert) =="
python backend/tests/test_trained_path.py
echo
echo "== gate 11/15: real CV evidence in the demo path (cv_feed, lines 42+44) =="
python backend/tests/test_cv_feed.py
echo
echo "== gate 12/15: live public-MQTT feed unit (deterministic, no network) =="
python backend/tests/smoke_live_feed_unit.py
echo
echo "== gate 13/15: real-hardware edge-node monitor + API + manifest honesty =="
python backend/tests/test_edge_node.py
echo
echo "== gate 14/15: DemoDriver beat-timing regression (full run(), line 57) =="
python backend/tests/test_demo_driver.py
echo
echo "== gate 15/15: exact demo-arc values re-pinned against real data (line 73) =="
python scripts/verify_demo_arc.py
echo
echo "== ALL 15 GATES PASS =="
