#!/usr/bin/env bash
# Unified backend test runner — one command for every standalone test file.
#   bash scripts/run_tests.sh
#
# The backend test suite is a set of standalone scripts (each with its own
# PASS/FAIL counters and non-zero exit on failure), not pytest modules.  This
# runner executes ALL of them in a deterministic order and fails the run if any
# one fails — the superset of the merge gate (scripts/verify_gate.sh).  CI runs
# this (see .github/workflows/ci.yml).
set -uo pipefail
cd "$(dirname "$0")/.."

# NEW-02: the site-temperature probe (Open-Meteo) is display-only, but the test
# suite must stay deterministic and network-free — force the offline fallback.
export VITISH_SITE_TEMP_DISABLE=1

TESTS=(
  backend/tests/smoke_test.py
  backend/tests/smoke_live_feed_unit.py
  backend/tests/test_api_routes.py
  backend/tests/test_bugfix_regression.py
  backend/tests/test_condition.py
  backend/tests/test_crack_width.py
  backend/tests/test_cv_feed.py
  backend/tests/test_demo_arc.py
  backend/tests/test_demo_driver.py
  backend/tests/test_deterioration.py
  backend/tests/test_fleet_learning.py
  backend/tests/test_edge_node.py
  backend/tests/test_manifest.py
  backend/tests/test_contract_parity.py
  backend/tests/test_condition_report.py
  backend/tests/test_security.py
  backend/tests/test_seeded_defect.py
  backend/tests/test_site_temperature.py
  backend/tests/test_stiffness.py
  backend/tests/test_telegram_alerts.py
  backend/tests/test_temperature.py
  backend/tests/test_trained_path.py
  backend/tests/test_deconfounding.py
  backend/tests/test_pg_failover.py
  backend/tests/test_multi_bridge.py
  backend/tests/test_honesty_gate.py
  backend/tests/test_perf_regression.py
  backend/scripts/e2e_stack_smoke.py
  scripts/verify_demo_arc.py
)

FAILED=0
TMPOUT=$(mktemp)
for t in "${TESTS[@]}"; do
  echo "== ${t} =="
  if ! python "$t" 2>&1 | tee "$TMPOUT"; then
    echo "!! FAILED: ${t}"
    FAILED=1
  fi
  # PostHackathon TEST-F3: a trained-ML gate that prints TRAINED_REAL_DATA=SKIP
  # is honest locally, but on CI it is a FAIL — the committed fixture must make
  # the gate RUN real evidence (no silent SKIP on a fresh clone).
  if [ "${CI:-0}" = "1" ] && grep -q "TRAINED_REAL_DATA=SKIP" "$TMPOUT"; then
    echo "!! CI=1: ${t} printed TRAINED_REAL_DATA=SKIP — the committed Z24 "
    echo "   fixture (data/z24/fixture/) must make it TRAINED_REAL_DATA=RUN."
    FAILED=1
  fi
  echo
done
rm -f "$TMPOUT"

echo "== ALL TESTS DONE =="
if [ "$FAILED" -ne 0 ]; then
  echo "!! one or more tests failed"
  exit 1
fi
echo "== ALL 29 TEST FILES PASS =="
