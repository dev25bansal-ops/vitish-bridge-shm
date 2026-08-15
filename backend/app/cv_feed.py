"""
VITISH 2026 · PS#99 SHM — real CV crack evidence for the demo path (ROADMAP line 42).

The storyboard's crack beats no longer fire scripted ``cmd:cv`` values. At each
crack beat the demo runs ONE real CC0 crack photo through the trained
``crack_seg.pt`` (STRICT YOLO-seg — the heuristic is never consulted, line 39)
and maps the top detection's confidence and normalized crack area to the cv
sub-index that BHI fusion consumes.

Deterministic mapping (fixed, monotone in both inputs, documented here):
    cv = clamp(0.45 * conf + 1.80 * area_norm, 0, 1)
  * conf      — top detection confidence from crack_seg.pt (real model output)
  * area_norm — top-detection mask area / frame area (real segmentation output)

Demo frames: ``data/cv/demo_frames/`` — CC0 CrackSeg9k-derived val photos
(same source as training, so in-distribution), selected so the real model
output lands on the storyboard's cv anchors:
  * mild_crack.jpg    -> cv ~ 0.31   (beat "crack-detected", was scripted 0.30)
  * severe_crack.jpg  -> cv ~ 0.57   (beat "bhi-drop",       was scripted 0.55)
The pinned arc (BHI 87.1 -> ... -> RED) is preserved to within ~1 BHI point;
``test_demo_arc.py`` still pins the exact scripted trajectory independently.

Honesty rule (never violated — see vault/08-Startup/Company-Project.md §14/§15):
the inference is REAL (real pixels, real model, real outputs). Only the FRAME
SELECTION is curated — a deterministic demo needs a repeatable storyboard, and
the two chosen frames are real crack photos whose actual model outputs happen
to sit at the storyboard anchors. Every emitted value is the model's real output
for the chosen input; nothing is fabricated. If weights/frames are missing or
inference fails, the scripted value is used and tagged ``source='cv_feed-fallback'``
(never silent — the ledger row stays honest).

This module also owns the process-wide cached CrackDetector so the demo path and
``?run_seg=1`` share one ~92 MB model (ROADMAP line 44).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_FRAMES = _REPO_ROOT / "data" / "cv" / "demo_frames"
WEIGHTS = _REPO_ROOT / "models" / "weights" / "crack_seg.pt"

# Lower than the interactive default so faint cracks still register; we only
# read the TOP detection, which for the curated demo frames is well above 0.5.
DETECT_CONF = 0.10
DETECT_IOU = 0.45

log = logging.getLogger(__name__)

# -- cached detector ----------------------------------------------------------
_detector: Optional[Any] = None
_detector_lock = threading.Lock()


def get_detector() -> Any:
    """Return the process-wide strict CrackDetector, building it once.

    Shared by the demo path and ``?run_seg=1`` so the 92 MB model is loaded a
    single time per process (ROADMAP line 44). Not thread-cached for writes
    beyond the lock — building is idempotent and callers never mutate it.
    """
    global _detector
    if _detector is not None:
        return _detector
    with _detector_lock:
        if _detector is None:
            from models.cv.inference import CrackDetector
            _detector = CrackDetector(weights_path=WEIGHTS, conf=DETECT_CONF,
                                      iou=DETECT_IOU)
    return _detector


def reset_detector() -> None:
    """Drop the cached detector (test seam / source-change reset)."""
    global _detector
    with _detector_lock:
        _detector = None


# -- detection -> cv evidence -------------------------------------------------
def cv_from_detection(conf: float, area_norm: float) -> float:
    """Deterministic detection->cv mapping (documented in the module docstring).

    Monotone increasing in both confidence and normalized crack area; clamped
    to [0, 1]. This is the ONE place the storyboard anchor is realized.
    """
    return max(0.0, min(1.0, 0.45 * float(conf) + 1.80 * float(area_norm)))


def evidence(frame_name: str, fallback_cv: float = 0.30) -> Dict[str, Any]:
    """Run ONE real demo frame through the strict YOLO -> cv evidence dict.

    Never raises. On success returns the real model's output with
    ``fallback=False``; on any failure (missing frame/weights, no detection,
    inference error) returns the scripted value with ``fallback=True`` and a
    reason, so the caller can publish honestly-tagged evidence.
    """
    import cv2

    frame_path = DEMO_FRAMES / frame_name
    try:
        det = get_detector()
        img = cv2.imread(str(frame_path))
        if img is None:
            raise FileNotFoundError(f"demo frame missing: {frame_path}")
        dets = det.detect(img, return_yolo_only=True)  # strict: YOLO only (line 39)
        if not dets:
            raise RuntimeError(f"strict YOLO found no detection on {frame_name}")
        top = max(dets, key=lambda d: d["conf"])
        conf = float(top["conf"])
        area_norm = float(top["area_px"]) / float(img.shape[0] * img.shape[1])
        cv = cv_from_detection(conf, area_norm)
        return {
            "cv": round(cv, 3),
            "conf": round(conf, 3),
            "area_norm": round(area_norm, 5),
            "frame": frame_name,
            "model": "crack_seg.pt",
            "source": "cv_feed",
            "mode": getattr(det, "mode", "yolo-seg"),
            "fallback": False,
        }
    except Exception as exc:
        log.warning("cv_feed: real inference unavailable (%s); scripted fallback %.2f",
                    exc, float(fallback_cv))
        return {
            "cv": float(fallback_cv),
            "conf": 0.0,
            "area_norm": 0.0,
            "frame": frame_name,
            "model": "scripted-fallback",
            "source": "cv_feed-fallback",
            "mode": "scripted",
            "fallback": True,
            "reason": str(exc),
        }
