"""
VITISH 2026 · PS#99 SHM — cv_feed unit test (ROADMAP lines 42 + 44).

Run from backend/:  python tests/test_cv_feed.py

Proves the real-CV-evidence path deterministically:
  1. The detection->cv mapping (cv_from_detection) is monotone, clamped, and
     anchors the storyboard (mild -> ~0.31, severe -> ~0.57).
  2. evidence() runs the REAL curated frames through the strict YOLO and emits
     the real model outputs (cv/conf/area_norm) with source='cv_feed'. When
     crack_seg.pt is absent (fresh clone — *.pt is gitignored) or inference
     fails, it returns the scripted value tagged cv_feed-fallback, never raising.
  3. Determinism: two calls on the same frame give identical outputs.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import cv_feed  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


def test_mapping():
    print("== cv_from_detection mapping ==")
    # monotone: higher conf or higher area never lowers cv
    check("monotone in conf", cv_feed.cv_from_detection(0.9, 0.01) > cv_feed.cv_from_detection(0.5, 0.01))
    check("monotone in area", cv_feed.cv_from_detection(0.5, 0.10) > cv_feed.cv_from_detection(0.5, 0.01))
    check("clamped low", cv_feed.cv_from_detection(0.0, 0.0) == 0.0)
    check("clamped high", cv_feed.cv_from_detection(1.0, 0.5) == 1.0)
    # storyboard anchors land within tolerance of the scripted values
    m = cv_feed.cv_from_detection(0.625, 0.0172)
    s = cv_feed.cv_from_detection(0.929, 0.0846)
    check("mild maps ~0.30", abs(m - 0.30) < 0.05, f"got {m:.3f}")
    check("severe maps ~0.55", abs(s - 0.55) < 0.05, f"got {s:.3f}")
    check("mild < severe", m < s)


def test_evidence():
    print("== evidence() real frames (strict YOLO) ==")
    mild = cv_feed.evidence("mild_crack.jpg", 0.30)
    severe = cv_feed.evidence("severe_crack.jpg", 0.55)
    weights_present = cv_feed.WEIGHTS.exists()
    frames_present = (cv_feed.DEMO_FRAMES / "mild_crack.jpg").exists()
    if weights_present and frames_present:
        check("mild real (not fallback)", not mild["fallback"], str(mild))
        check("severe real (not fallback)", not severe["fallback"], str(severe))
        check("mild source cv_feed", mild["source"] == "cv_feed")
        check("mild conf matches README", abs(mild["conf"] - 0.625) < 0.05,
              f"got {mild['conf']}")
        check("severe conf matches README", abs(severe["conf"] - 0.929) < 0.05,
              f"got {severe['conf']}")
        check("mild cv ~0.30", abs(mild["cv"] - 0.30) < 0.05, f"got {mild['cv']}")
        check("severe cv ~0.55", abs(severe["cv"] - 0.55) < 0.05, f"got {severe['cv']}")
        check("mild < severe cv", mild["cv"] < severe["cv"])
        check("model named", mild["model"] == "crack_seg.pt")
        # determinism: same input, same output
        again = cv_feed.evidence("mild_crack.jpg", 0.30)
        check("deterministic", again == mild)
    else:
        # fresh clone without the gitignored weights: must fall back, never raise
        print("  [skip] crack_seg.pt/frames absent -> asserting fallback only")
        check("mild falls back (tagged)", mild["fallback"] and mild["source"] == "cv_feed-fallback")
        check("mild fallback cv is scripted value", mild["cv"] == 0.30)
        check("severe falls back (tagged)", severe["fallback"] and severe["source"] == "cv_feed-fallback")


def test_fallback_robustness():
    print("== evidence() failure path ==")
    res = cv_feed.evidence("no_such_frame.jpg", 0.30)
    check("missing frame -> fallback", res["fallback"] is True)
    check("missing frame -> scripted cv", res["cv"] == 0.30)
    check("missing frame -> tagged source", res["source"] == "cv_feed-fallback")
    check("missing frame -> reason present", bool(res.get("reason")))


def main():
    test_mapping()
    test_evidence()
    test_fallback_robustness()
    print()
    print("=" * 48)
    print(f" cv_feed unit: {PASS} passed, {FAIL} failed")
    if FAILURES:
        for f in FAILURES:
            print(f"   FAILED: {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
