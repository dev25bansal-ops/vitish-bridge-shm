"""
D1-4 gate — Markov deterioration with empirical LTBP priors.

The deterioration overlay is a *fleet prior + Markov projection*, explicitly
NOT a certified RUL or Paris-law forecast.  This gate pins:
  * the empirical transition matrices load and are row-stochastic,
  * the BHI->NBI mapping is the documented model assumption,
  * a poor bridge triggers "next inspection" fast, a good bridge slow,
  * the honesty labels are always present.

Run:  python backend/tests/test_deterioration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from app.deterioration import (  # noqa: E402
    bridge_deterioration,
    condition_from_bhi,
    load_priors,
    next_inspection,
    priors_label,
    project,
    transition_matrix,
)

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


def test_priors() -> None:
    print("[deterioration] empirical LTBP priors")
    d = load_priors()
    check("summary has real provenance",
          "FHWA InfoBridge" in str(d.get("provenance", "")), str(d.get("provenance")))
    check("pilot longitudinal bridges present",
          int(d.get("pilot_bridges", 0)) >= 40, str(d.get("pilot_bridges")))
    for rating in ("super", "sub"):
        P, prov = transition_matrix(rating)
        check(f"{rating}: 10x10 matrix", P.shape == (10, 10), str(P.shape))
        check(f"{rating}: row-stochastic (rows sum to 1)",
              np.allclose(P.sum(axis=1), 1.0, atol=1e-9),
              str(P.sum(axis=1).round(3)))
        check(f"{rating}: has empirical rows",
              len(prov["empirical_rows"]) >= 3, str(prov["empirical_rows"]))
        check(f"{rating}: small-n rows flagged",
              "small_n_defaulted_rows" in prov, str(prov.keys()))


def test_mapping() -> None:
    print("[deterioration] BHI -> NBI condition mapping (model assumption)")
    check("BHI 87 -> NBI 8", condition_from_bhi(87.0) == 8, str(condition_from_bhi(87.0)))
    check("BHI 67 -> NBI 6", condition_from_bhi(67.0) == 6, str(condition_from_bhi(67.0)))
    check("BHI 34 -> NBI 4", condition_from_bhi(34.0) == 4, str(condition_from_bhi(34.0)))
    check("clamped 0..9", condition_from_bhi(-5) == 1 and condition_from_bhi(200) == 9,
          str((condition_from_bhi(-5), condition_from_bhi(200))))


def test_projection() -> None:
    print("[deterioration] Markov projection")
    rows = project("super", 7, years=25)
    check("one row per year", len(rows) == 25, str(len(rows)))
    r0, r_end = rows[0], rows[-1]
    for r in (r0, r_end):
        check("dist sums to ~1", abs(sum(r["dist"]) - 1.0) < 1e-3,
              str(sum(r["dist"])))
        check("expected within [0,9]", 0 <= r["expected"] <= 9, str(r["expected"]))
    # mid-life concrete superstructure: expected condition drifts down over 25y
    check("expected declines over 25y",
          r_end["expected"] <= r0["expected"] + 0.05,
          f"{r0['expected']} -> {r_end['expected']}")
    # p_poor (P(NBI<=4)) rises as it ages
    check("p_poor non-decreasing", r_end["p_poor"] >= r0["p_poor"],
          f"{r0['p_poor']} -> {r_end['p_poor']}")
    # uncertainty fan is sane
    check("p10 <= expected <= p90", r_end["p10"] <= r_end["expected"] <= r_end["p90"],
          str((r_end["p10"], r_end["expected"], r_end["p90"])))


def test_next_inspection() -> None:
    print("[deterioration] next-inspection trigger")
    poor = next_inspection("super", 4)      # already poor -> trigger soon
    good = next_inspection("super", 8)      # good -> trigger much later
    check("poor bridge triggers fast", poor is not None and poor <= 8,
          str(poor))
    check("good bridge triggers later (or never in 100y)",
          good is None or good > poor, str((poor, good)))
    # same bridge on sub rating (sub deteriorates slower in the real data)
    good_sub = next_inspection("sub", 8)
    check("sub rating at least as slow as super",
          good_sub is None or good_sub >= (good or 0),
          str((good, good_sub)))


def test_payload() -> None:
    print("[deterioration] API payload honesty")
    p = bridge_deterioration("reg-01", 74.0, years=20)
    check("priors label present", "empirical LTBP prior" in p["priors_label"],
          p["priors_label"])
    check("priors label function == constant (no merge)",
          priors_label() == "empirical LTBP prior, small n "
                             "(44 FHWA InfoBridge pilot bridges, 1993-2025)",
          priors_label())
    check("projection length = years", len(p["projection"]) == 20, str(len(p["projection"])))
    check("next-inspection rule stated",
          "first year" in p["next_inspection_rule"], p["next_inspection_rule"])
    check("not-a-RUL note present", "not a certified RUL" in p["note"], p["note"])
    check("current condition derived from BHI",
          p["current_condition"] == condition_from_bhi(74.0), str(p["current_condition"]))
    check("bridge id echoed", p["bridge"] == "reg-01", p["bridge"])


def main() -> int:
    try:
        test_priors()
        test_mapping()
        test_projection()
        test_next_inspection()
        test_payload()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("deterioration tests")
        import traceback
        print(f"  [ERROR] deterioration tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== deterioration gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
