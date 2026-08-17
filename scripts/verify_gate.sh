#!/usr/bin/env bash
# Merge gate — run before every push/merge. The demo arc must NEVER break.
#   bash scripts/verify_gate.sh
# Fails (non-zero exit) if any gate does not pass cleanly.
# Superset: scripts/run_tests.sh runs every standalone test file (17 backend
# tests + scripts/verify_demo_arc.py) in one command — CI uses that runner.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== gate 1/17: full smoke test (backend end-to-end) =="
python backend/tests/smoke_test.py
echo
echo "== gate 2/17: Z24 stiffness physics overlay (D1-2) =="
python backend/tests/test_stiffness.py
echo
echo "== gate 3/17: condition card from crack index (D1-3) =="
python backend/tests/test_condition.py
echo
echo "== gate 4/17: LTBP Markov deterioration (D1-4) =="
python backend/tests/test_deterioration.py
echo
echo "== gate 5/17: demo-arc regression (GREEN -> AMBER -> RED, pinned) =="
python backend/tests/test_demo_arc.py
echo
echo "== gate 6/17: temperature normalization of f1 (D2-10) =="
python backend/tests/test_temperature.py
echo
echo "== gate 7/17: data-realism manifest + synthetic channel models (D1-5) =="
python backend/tests/test_manifest.py
echo
echo "== gate 8/17: seeded-defect demo grounded in Z24/S101 (D2-12) =="
python backend/tests/test_seeded_defect.py
echo
echo "== gate 9/17: newer HTTP routes (live/manifest/stiffness/seeded-defect/deterioration/condition/config) =="
python backend/tests/test_api_routes.py
echo
echo "== gate 10/17: trained-path regression (retrained 2026-08-15, separation asserted) =="
python backend/tests/test_trained_path.py
echo
echo "== gate 11/17: real CV evidence in the demo path (cv_feed, lines 42+44) =="
python backend/tests/test_cv_feed.py
echo
echo "== gate 12/17: live public-MQTT feed unit (deterministic, no network) =="
python backend/tests/smoke_live_feed_unit.py
echo
echo "== gate 13/17: real-hardware edge-node monitor + recorder + API + manifest honesty (esp32-1 + esp01-1) =="
python backend/tests/test_edge_node.py
echo
echo "== gate 14/17: DemoDriver beat-timing regression (full run(), line 57) =="
python backend/tests/test_demo_driver.py
echo
echo "== gate 15/17: exact demo-arc values re-pinned against real data (line 73) =="
python scripts/verify_demo_arc.py
echo
echo "== gate 16/17: environmental de-confounding (floor flat on temperature-only, fires on damage; trained limits documented) =="
python backend/tests/test_deconfounding.py
echo
echo "== gate 17/18: out-of-band alert dispatch (Telegram, NEW-01 — env-token, fail-open, throttled, honest wording) =="
python backend/tests/test_telegram_alerts.py
echo
echo "== gate 18/18: BHI contract parity backend<->twin (ENH-10: /api/config block, twin constants, re-run of pinned computeBhi assertions) + MemoryStore bridge-tag (ENH-01/BUG-01) =="
python backend/tests/test_contract_parity.py
echo
echo "== ALL 18 GATES PASS =="
