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

TESTS=(
  backend/tests/smoke_test.py
  backend/tests/smoke_live_feed_unit.py
  backend/tests/test_api_routes.py
  backend/tests/test_condition.py
  backend/tests/test_cv_feed.py
  backend/tests/test_demo_arc.py
  backend/tests/test_demo_driver.py
  backend/tests/test_deterioration.py
  backend/tests/test_edge_node.py
  backend/tests/test_manifest.py
  backend/tests/test_seeded_defect.py
  backend/tests/test_stiffness.py
  backend/tests/test_temperature.py
  backend/tests/test_trained_path.py
  scripts/verify_demo_arc.py
)

FAILED=0
for t in "${TESTS[@]}"; do
  echo "== ${t} =="
  if ! python "$t"; then
    echo "!! FAILED: ${t}"
    FAILED=1
  fi
  echo
done

echo "== ALL TESTS DONE =="
if [ "$FAILED" -ne 0 ]; then
  echo "!! one or more tests failed"
  exit 1
fi
echo "== ALL 15 TEST FILES PASS =="
