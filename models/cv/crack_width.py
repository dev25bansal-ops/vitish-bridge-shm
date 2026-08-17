"""
VITISH 2026 · PS#99 SHM — crack-width metrology (pixel-scale, UNcalibrated).

§7.6 item 18: crack-width metrology from the real YOLO-seg binary mask.

A crack's physical width in millimetres is what a structural inspector
reports.  A sensor image alone cannot give mm: width-in-pixels depends on
distance to the camera, lens focal length, and sensor pixel pitch.  What we
CAN measure honestly is the mask's geometric width **in image pixels**:

    local width(p) = 2 * distance_from(p, background)     p on the medial axis
    (Euclidean distance transform sampled on the Zhang–Suen skeleton)

Data products:
  * ``crack_pixel_width(mask_bin)`` -> per-mask width statistics in px
    (mean / median / max over the medial axis, skeleton length in px).
  * Integrated into ``models/fusion/condition.py`` evidence and
    ``app/cv_feed.py`` evidence, always tagged ``unit: "px"`` with
    ``calibrated_mm: None``.

HONESTY RULE — this is NOT certified metrology (never present it as mm):
  * Width is in image pixels of the sourced frame, with no calibration target.
  * Converting px -> mm requires a known spatial calibration (a scale target /
    feature of known physical size in the same plane).  Until the demo carries
    one, the output stays labelled "uncalibrated pixel width".  See
    vault/08-Startup/Company-Project.md §14/§15 and the item-18 annotation in
    docs/COMPREHENSIVE-ANALYSIS.md.
"""
from __future__ import annotations

import numpy as np

WIDTH_HONESTY_NOTE = (
    "uncalibrated pixel width (no calibration target) — px, not mm; "
    "requires a known physical scale to convert, and is a relative reading, "
    "never certified metrology."
)


def _zhang_suen(img_bin: np.ndarray) -> np.ndarray:
    """Zhang–Suen binary thinning -> medial skeleton (0/1 uint8).

    Vectorized with numpy slicing (no scipy/skimage dependency).  Deletes
    border pixels iteratively while preserving connectivity; terminates when
    an iteration deletes nothing.  The result is a 1-px-wide medial line of a
    connected foreground region — the standard skeleton for crack width.

    Each DELETE STEP re-pads from the CURRENT image, so step 2 sees step 1's
    deletions — the serial algorithm.  (Evaluating both steps against one stale
    snapshot over-thins: a 2-row band collapses to nothing instead of leaving
    its 1-px medial line.)
    """
    img = (img_bin > 0).astype(np.uint8)
    h, w = img.shape
    if h < 3 or w < 3:
        return img.copy()
    while True:
        changed = 0
        for step in (1, 2):
            a = np.pad(img, 1)
            # 8-neighborhood of p1 at (y, x):
            #             p2 (y-1,x)        p3 (y-1,x+1)
            #   p8 (y,x-1)        p1          p4 (y,x+1)
            #             p7 (y+1,x-1)      p6 (y+1,x)        p5 (y+1,x+1)
            p2 = a[0:h, 1:w + 1]
            p3 = a[0:h, 2:w + 2]
            p4 = a[1:h + 1, 2:w + 2]
            p5 = a[2:h + 2, 2:w + 2]
            p6 = a[2:h + 2, 1:w + 1]
            p7 = a[2:h + 2, 0:w]
            p8 = a[1:h + 1, 0:w]
            p9 = a[0:h, 0:w]
            B = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9               # non-zero count
            # 0->1 transitions around p1 (INTEGER sum — numpy 'bool + bool'
            # is bitwise-OR, which would collapse this count to a boolean)
            A = sum((t.astype(np.uint8) for t in (
                (p2 == 0) & (p3 == 1), (p3 == 0) & (p4 == 1),
                (p4 == 0) & (p5 == 1), (p5 == 0) & (p6 == 1),
                (p6 == 0) & (p7 == 1), (p7 == 0) & (p8 == 1),
                (p8 == 0) & (p9 == 1), (p9 == 0) & (p2 == 1))), 0)
            if step == 1:  # delete N/W-boundary + corner pixels
                cond_c = p2 * p4 * p6 == 0
                cond_d = p4 * p6 * p8 == 0
            else:          # delete S/E-boundary + corner pixels
                cond_c = p2 * p4 * p8 == 0
                cond_d = p2 * p6 * p8 == 0
            del_mask = (B >= 2) & (B <= 6) & (A == 1) & cond_c & cond_d & (img == 1)
            img[del_mask] = 0
            changed += int(del_mask.sum())
        if changed == 0:
            break
    return img


def crack_pixel_width(mask_bin: np.ndarray) -> dict | None:
    """Geometric crack width statistics in image pixels from a binary mask.

    ``mask_bin``: 2-D integer/float array where non-zero = foreground (the
    ``mask`` np.uint8 field of a detection dict from models/cv/inference.py).

    Returns a dict (<stats>) or ``None`` when the mask is empty / degenerate
    (too little foreground or no skeleton).  Every return carries the honesty
    keys ``unit: "px"`` and ``calibrated_mm: None``.

    Method: Euclidean distance transform sampled on the Zhang–Suen medial
    skeleton.  At a medial pixel the local width is 2 * (distance to the
    nearest background pixel) — shape-consistent for bars, blobs and forks,
    which the naive area/length ratio is not.
    """
    mask = (mask_bin > 0)
    if mask.ndim != 2 or int(mask.sum()) < 5:
        return None
    skel = _zhang_suen(mask.astype(np.uint8))
    n_skel = int(skel.sum())
    if n_skel == 0:
        return None
    try:
        import cv2
    except ImportError:  # pragma: no cover - cv2 is a hard runtime dep elsewhere
        raise
    dist = cv2.distanceTransform(mask.astype(np.uint8) * 255, cv2.DIST_L2, 5)
    local_w = 2.0 * dist[skel.astype(bool)]
    # sub-pixel spurs left at squared-off ends read ~1-2 px; keep >= 1 px so
    # they do not drag the mean toward zero, but report median as primary.
    local_w = local_w[local_w >= 1.0]
    if local_w.size == 0:
        return None
    return {
        "width_mean_px": round(float(local_w.mean()), 2),
        "width_median_px": round(float(np.median(local_w)), 2),
        "width_p90_px": round(float(np.percentile(local_w, 90)), 2),
        "width_max_px": round(float(local_w.max()), 2),
        "skeleton_len_px": n_skel,
        "unit": "px",
        "calibrated_mm": None,
        "note": WIDTH_HONESTY_NOTE,
    }


def aggregate_width(dets: list[dict]) -> dict | None:
    """Aggregate per-detection width stats (median of medians, worst max).

    ``dets``: detection dicts (models/cv/inference) that may carry ``mask``.
    Returns None when no detection has a measurable mask, so callers can keep
    the evidence block honest: no numbers -> no width claim.
    """
    medians = []
    worst_max = 0.0
    measured = 0
    for d in dets:
        m = d.get("mask")
        if m is None:
            continue
        w = crack_pixel_width(m)
        if w is None:
            continue
        measured += 1
        medians.append(float(w["width_median_px"]))
        worst_max = max(worst_max, float(w["width_max_px"]))
    if not medians:
        return None
    return {
        "crack_width_px": {
            "median_px": round(float(np.median(medians)), 2),
            "max_px": round(float(worst_max), 2),
            "unit": "px",
            "calibrated_mm": None,
        },
        "measured_detections": measured,
        "note": WIDTH_HONESTY_NOTE,
    }