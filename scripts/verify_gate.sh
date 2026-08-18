#!/usr/bin/env bash
# Merge gate — run before every push/merge. The demo arc must NEVER break.
#   bash scripts/verify_gate.sh
# Fails (non-zero exit) if any gate does not pass cleanly.
# Superset: scripts/run_tests.sh runs every standalone test file (the 29-file
# suite: 28 backend/tests files + scripts/verify_demo_arc.py) in one command —
# CI uses that runner.
set -euo pipefail
cd "$(dirname "$0")/.."

# NEW-02: force the site-temperature probe off in the gate run — the suite is
# deterministic and air-gapped (the measured Open-Meteo path is unit-tested
# with a faked HTTP client instead).
export VITISH_SITE_TEMP_DISABLE=1

echo "== gate 1/24: full smoke test (backend end-to-end) =="
python backend/tests/smoke_test.py
echo
echo "== gate 2/24: Z24 stiffness physics overlay (D1-2) =="
python backend/tests/test_stiffness.py
echo
echo "== gate 3/24: condition card from crack index (D1-3) =="
python backend/tests/test_condition.py
echo
echo "== gate 4/24: LTBP Markov deterioration (D1-4) =="
python backend/tests/test_deterioration.py
echo
echo "== gate 5/24: demo-arc regression (GREEN -> AMBER -> RED, pinned) =="
python backend/tests/test_demo_arc.py
echo
echo "== gate 6/24: temperature normalization of f1 (D2-10) =="
python backend/tests/test_temperature.py
echo
echo "== gate 7/24: data-realism manifest + synthetic channel models (D1-5) =="
python backend/tests/test_manifest.py
echo
echo "== gate 8/24: seeded-defect demo grounded in Z24/S101 (D2-12) =="
python backend/tests/test_seeded_defect.py
echo
echo "== gate 9/24: newer HTTP routes (live/manifest/stiffness/seeded-defect/deterioration/condition/config) =="
python backend/tests/test_api_routes.py
echo
echo "== gate 10/24: trained-path regression (retrained 2026-08-15, separation asserted) =="
python backend/tests/test_trained_path.py
echo
echo "== gate 11/24: real CV evidence in the demo path (cv_feed, lines 42+44) =="
python backend/tests/test_cv_feed.py
echo
echo "== gate 12/24: live public-MQTT feed unit (deterministic, no network) =="
python backend/tests/smoke_live_feed_unit.py
echo
echo "== gate 13/24: real-hardware edge-node monitor + recorder + API + manifest honesty (esp32-1 + esp01-1) =="
python backend/tests/test_edge_node.py
echo
echo "== gate 14/24: DemoDriver beat-timing regression (full run(), line 57) =="
python backend/tests/test_demo_driver.py
echo
echo "== gate 15/24: exact demo-arc values re-pinned against real data (line 73) =="
python scripts/verify_demo_arc.py
echo
echo "== gate 16/24: environmental de-confounding (floor flat on temperature-only, fires on damage; trained limits documented) =="
python backend/tests/test_deconfounding.py
echo
echo "== gate 17/24: out-of-band alert dispatch (Telegram, NEW-01 — env-token, fail-open, throttled, honest wording) =="
python backend/tests/test_telegram_alerts.py
echo
echo "== gate 18/24: BHI contract parity backend<->twin (ENH-10: /api/config block, twin constants, re-run of pinned computeBhi assertions) + MemoryStore bridge-tag (ENH-01/BUG-01) =="
python backend/tests/test_contract_parity.py
echo
echo "== gate 19/24: §2.2 bug-fix regression (BUG-02 emit fallback on failed publish, BUG-03 malformed-accel drop, BUG-05 hero validate_accel strictness) =="
python backend/tests/test_bugfix_regression.py
echo
echo "== gate 20/24: crack-width metrology (item 18 — pixel-scale, UNcalibrated, honestly labelled px-not-mm) =="
python backend/tests/test_crack_width.py
echo
echo "== gate 21/24: fleet-prior learning loop (item 21 — observed-transitions store + append/merge, provenance-labelled) =="
python backend/tests/test_fleet_learning.py
echo
echo "== gate 22/24: §2.3 performance regression (PERF-01..08 — batched MC-dropout, coarse-grid f1 lookup, lazy grid, alpha LRU, deferred flush, broker probe TTL) =="
python backend/tests/test_perf_regression.py
echo
echo "== gate 23/24: §2.1 SEC hardening (SEC-01..04,06 — loopback compose binds + opt-in broker auth/ACL + token-gated demo route + WS origin validation + per-client cap) =="
python backend/tests/test_security.py
echo
echo "== gate 24/24: hosted public demo + cinematic landing (item 20 — static / + /twin mounts, honest-provenance hero film, hosted-demo SEC recipe, origin-aware twin) =="
python backend/tests/test_hosted_demo.py
echo
echo "== ALL 24 GATES PASS =="