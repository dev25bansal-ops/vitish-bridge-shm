"""
D1-3 gate — regulator condition card from the crack index.

The card maps segmentation detections -> crack index -> relative severity ->
condition state (NBI + post-Morandi-style risk class) with confidence.  It must
NEVER present a raw CV score as "condition": every card carries its source and
the not-a-certified-assessment label.

Run:  python backend/tests/test_condition.py
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

from models.fusion import condition as cond  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, condv: bool, extra: str = "") -> None:
    global PASS, FAIL
    if condv:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


def test_mapping() -> None:
    print("[condition] documented mapping (auditable thresholds)")
    check("no cracks -> NBI 9 Excellent",
          cond.condition_card([], mode="yolo-seg")["condition"]["nbi"] == 9)
    # 3 mild cracks -> moderate severity, NBI ~7, risk A/B
    mild = [{"conf": 0.6, "severity": 0.05}, {"conf": 0.5, "severity": 0.03}]
    card = cond.condition_card(mild, mode="yolo-seg")
    check("mild cracks -> light/moderate severity",
          card["severity"] in ("light", "moderate"), card["severity"])
    check("mild cracks -> NBI >= 7", card["condition"]["nbi"] >= 7,
          str(card["condition"]["nbi"]))
    # heavy crack load -> critical severity, NBI <= 4
    heavy = [{"conf": 0.95, "severity": 0.5}, {"conf": 0.9, "severity": 0.4},
             {"conf": 0.85, "severity": 0.3}]
    ch = cond.condition_card(heavy, mode="yolo-seg")
    check("heavy cracks -> severe/critical", ch["severity"] in ("severe", "critical"),
          ch["severity"])
    check("heavy cracks -> NBI <= 5", ch["condition"]["nbi"] <= 5,
          str(ch["condition"]["nbi"]))
    check("crack index monotone", ch["crack_index"] > card["crack_index"],
          f"{card['crack_index']} < {ch['crack_index']}")


def test_live_cv() -> None:
    print("[condition] live cv sub-index source (honest label)")
    card = cond.card_from_live_cv(0.42)
    check("source labeled live-cv-subindex", card["source"] == "live-cv-subindex",
          card["source"])
    check("never a raw cv score as condition", "condition" in card and "cv" not in card,
          str(card.keys()))
    check("confidence in [0.4,0.95]", 0.4 <= card["confidence"] <= 0.95,
          str(card["confidence"]))
    check("live cv uses index mapping", abs(card["crack_index"] - 0.42) < 1e-6,
          str(card["crack_index"]))
    check("honesty note present", "NEVER a certified structural assessment" in card["note"],
          card["note"])


def test_confidence_and_provenance() -> None:
    print("[condition] confidence + provenance")
    # yolo-seg + more detections -> higher confidence than heuristic + 1 det
    c_yolo = cond.confidence("yolo-seg", 4, 0.5)
    c_heur = cond.confidence("heuristic", 1, 0.5)
    check("yolo-seg confidence > heuristic", c_yolo > c_heur,
          f"{c_yolo} vs {c_heur}")
    card = cond.condition_card([{"conf": 0.9, "severity": 0.2}], mode="yolo-seg")
    check("detector mode echoed", card["detector_mode"] == "yolo-seg",
          card["detector_mode"])
    check("evidence count present", card["evidence"]["n_detections"] == 1,
          str(card["evidence"]))
    check("thresholds documented in module",
          hasattr(cond, "B_REF") and hasattr(cond, "NBI_PER_CI"),
          str((cond.B_REF, cond.NBI_PER_CI)))


def main() -> int:
    try:
        test_mapping()
        test_live_cv()
        test_confidence_and_provenance()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("condition tests")
        import traceback
        print(f"  [ERROR] condition tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== condition gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
