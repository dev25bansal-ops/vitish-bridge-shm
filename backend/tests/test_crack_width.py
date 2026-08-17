"""
VITISH 2026 · PS#99 SHM — crack-width metrology unit test (§7.6 item 18).

Run from backend/:  python tests/test_crack_width.py

Proves, deterministically and WITHOUT the YOLO model (no crack_seg.pt needed):
  1. crack_pixel_width() recovers the true geometric width of synthetic masks
     in PIXELS (bar, diagonal, blob) — the medial-axis + distance-transform
     method is shape-consistent.
  2. The output is HONESTLY labelled: unit == "px", calibrated_mm is None, and
     the note says it is not certified metrology.
  3. Degenerate masks (1 px, empty, <5 foreground px) -> None, never a number.
  4. condition_card() surfaces the aggregated width in evidence ONLY when
     detections carry measurable masks (no masks -> no width claim).
  5. cv_feed.evidence() carries crack_width_px for a real detection (fake
     detector injected — no model load) and None on the honest fallback path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import cv2

BACKEND = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
for _p in (BACKEND, ROOT, BACKEND / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from models.cv.crack_width import (  # noqa: E402
    WIDTH_HONESTY_NOTE,
    aggregate_width,
    crack_pixel_width,
    _zhang_suen,
)
from models.fusion import condition as cond_mod  # noqa: E402
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


def _bar(width: int, length: int, angle: float = 0.0) -> np.ndarray:
    """Solid bar mask (uint8 0/255) of given perpendicular width and length."""
    side = max(length, 96) + 32
    img = np.zeros((side, side), dtype=np.uint8)
    cv2.rectangle(img, (16, side // 2 - width // 2),
                  (16 + length, side // 2 + width // 2 - 1 + (width % 2)), 255, -1)
    if angle != 0.0:
        m = cv2.getRotationMatrix2D((side / 2, side / 2), angle, 1.0)
        img = cv2.warpAffine(img, m, (side, side), borderValue=0)
    return img


def test_width_recovers_pixels():
    print("== pixel width of synthetic masks ==")
    w = crack_pixel_width(_bar(12, 100))
    check("rect 12px: median recovered", 10 <= w["width_median_px"] <= 14,
          f"median={w['width_median_px']}")
    check("rect 12px: max == true width", 12 <= w["width_max_px"] <= 14,
          f"max={w['width_max_px']}")
    check("rect 12px: long skeleton", w["skeleton_len_px"] > 60,
          f"len={w['skeleton_len_px']}")

    w6 = crack_pixel_width(_bar(6, 90))
    check("rect 6px: median recovered", 4.5 <= w6["width_median_px"] <= 8,
          f"median={w6['width_median_px']}")

    wd = crack_pixel_width(_bar(9, 80, angle=35.0))
    check("diag 9px: median recovered", 5 <= wd["width_median_px"] <= 13,
          f"median={wd['width_median_px']}")
    check("diag: skeleton length", wd["skeleton_len_px"] > 50,
          f"len={wd['skeleton_len_px']}")

    # blob (filled disk) -> medial width ~= diameter
    img = np.zeros((96, 96), dtype=np.uint8)
    cv2.circle(img, (48, 48), 30, 255, -1)
    wc = crack_pixel_width(img)
    check("disk r30: median ~ diameter", 48 <= wc["width_median_px"] <= 66,
          f"median={wc['width_median_px']}")

    # honesty labels
    check("honesty unit px", w["unit"] == "px")
    check("honesty calibrated None", w["calibrated_mm"] is None)
    check("honesty note present", "uncalibrated" in w["note"])

    # skeleton is a single-px medial line for a horizontal bar
    skel = _zhang_suen(_bar(12, 100))
    rows = np.nonzero(skel.any(axis=1))[0]
    check("skeleton single row thick", rows.max() - rows.min() <= 2,
          f"rows={rows.min()}..{rows.max()}")


def test_degenerate_masks():
    print("== degenerate masks -> None ==")
    check("empty mask None", crack_pixel_width(np.zeros((32, 32), dtype=np.uint8)) is None)
    check("1px mask None", crack_pixel_width(np.array([[255]], dtype=np.uint8)) is None)
    tiny = np.zeros((32, 32), dtype=np.uint8)
    tiny[5:7, 5:7] = 255  # 4 px
    check("tiny <5px None", crack_pixel_width(tiny) is None)
    check("2D requirement (1-D input) None",
          crack_pixel_width(np.zeros(10, dtype=np.uint8)) is None)


def test_condition_card_evidence():
    print("== condition_card width evidence ==")
    mask = _bar(12, 80)
    dets = [{"conf": 0.9, "severity": 0.3, "mask": mask},
            {"conf": 0.8, "severity": 0.2, "mask": np.roll(mask, 5, axis=0)}]
    card = cond_mod.condition_card(dets, mode="yolo-seg")
    cw = card["evidence"].get("crack_width")
    check("card evidence has crack_width", cw is not None, str(card["evidence"].keys()))
    check("card width unit px", cw["crack_width_px"]["unit"] == "px")
    check("card width calibrated None", cw["crack_width_px"]["calibrated_mm"] is None)
    check("card width measured both dets", cw["measured_detections"] == 2)
    check("card severity still computed", card["condition"]["nbi"] is not None)

    nogate = cond_mod.condition_card([{"conf": 0.9, "severity": 0.3}], mode="yolo-seg")
    check("no masks -> no width claim", "crack_width" not in nogate["evidence"])
    check("no-mask card still valid", nogate["confidence"] is not None)

    none = cond_mod.condition_card(dets=[], cv_subindex=0.4, mode="live-cv-subindex")
    check("live subindex card has no width", "crack_width" not in none["evidence"])


def test_cv_feed_evidence_width():
    print("== cv_feed.evidence() width field (fake detector, no model) ==")
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="crackwidth_"))
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    cv2.imwrite(str(tmp / "f.jpg"), frame)
    old_frames = cv_feed.DEMO_FRAMES
    old_det = cv_feed._detector

    class _FakeDet:
        mode = "yolo-seg"

        def detect(self, img, return_yolo_only=True):
            mask = _bar(12, 60)
            return [{"conf": 0.91, "area_px": int(np.count_nonzero(mask)),
                     "mask": mask, "cls": "crack", "box": [1, 1, 40, 40],
                     "mask_rle": "", "severity": 0.3}]

    try:
        cv_feed.DEMO_FRAMES = tmp
        cv_feed._detector = _FakeDet()
        res = cv_feed.evidence("f.jpg", 0.30)
        check("real path not fallback", res["fallback"] is False)
        check("width present", res["crack_width_px"] is not None,
              str(res.get("crack_width_px")))
        check("width median ~12px", 10 <= res["crack_width_px"]["width_median_px"] <= 14,
              f"median={res['crack_width_px']['width_median_px']}")
        check("width unit px", res["crack_width_px"]["unit"] == "px")
        check("width calibrated None", res["crack_width_px"]["calibrated_mm"] is None)

        # fallback path (missing frame) -> width None, honest schema stable
        fb = cv_feed.evidence("nope.jpg", 0.30)
        check("fallback flagged", fb["fallback"] is True)
        check("fallback width None", fb["crack_width_px"] is None)
    finally:
        cv_feed.DEMO_FRAMES = old_frames
        cv_feed._detector = old_det


def test_aggregate():
    print("== aggregate_width ==")
    mask = _bar(12, 80)
    agg = aggregate_width([{"mask": mask}, {"mask": np.roll(mask, 3, axis=1)}])
    check("aggregate present", agg is not None)
    check("aggregate median px", 10 <= agg["crack_width_px"]["median_px"] <= 14)
    check("aggregate allows px honesty", agg["crack_width_px"]["unit"] == "px")
    check("aggregate no dets -> None", aggregate_width([]) is None)
    check("aggregate no masks -> None", aggregate_width([{"severity": 0.5}]) is None)


def main():
    test_width_recovers_pixels()
    test_degenerate_masks()
    test_condition_card_evidence()
    test_cv_feed_evidence_width()
    test_aggregate()
    print()
    print("=" * 48)
    print(f" crack-width unit: {PASS} passed, {FAIL} failed")
    if FAILURES:
        for f in FAILURES:
            print(f"   FAILED: {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())