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
_detector_failed = False
_detector_lock = threading.Lock()


def get_detector() -> Optional[Any]:
    """Return the process-wide strict CrackDetector, building it once (or None
    while a prebuild is in flight / after a build failure).

    Shared by the demo path and ``?run_seg=1`` so the 92 MB model is loaded a
    single time per process (ROADMAP line 44).  PERF-03: a first call used to
    hold the lock for the full torch load (~4.7s on disk) — a stall on the
    fusion thread at the t=45 cv beat.  ``prebuild_detector()`` (run_all) now
    kicks the load off at startup on a daemon thread; ``get_detector`` never
    blocks on that: while the build is in flight it returns None (a lock-reentry
    deadlock is also avoided — ``evidence`` calls this from a load catch).  The
    caller treats None like "model not ready" and falls back to scripted cv,
    which is the honest offline behavior.  Idempotent; a build failure latches
    ``_detector_failed``.
    """
    global _detector, _detector_failed
    if _detector is not None:
        return _detector
    if _detector_failed:
        return None
    if not _detector_lock.acquire(blocking=False):
        return None                       # prebuild still in flight
    try:
        if _detector is None and not _detector_failed:
            from models.cv.inference import CrackDetector
            _detector = CrackDetector(weights_path=WEIGHTS, conf=DETECT_CONF,
                                      iou=DETECT_IOU)
    except Exception as exc:              # pragma: no cover - only when models/ is broken
        log.warning("cv_feed: detector init failed (%s); scripted fallback", exc)
        _detector_failed = True
    finally:
        _detector_lock.release()
    return _detector


def prebuild_detector() -> None:
    """Eagerly load the crack model on a background daemon thread (PERF-03).

    The t=45 storyboard cv beat used to pay a ~4.7s torch.load of the 92 MB
    crack_seg.pt inline, on the fusion scoring thread.  Startup (run_all) now
    fires this so the model is warm before the demo reaches the first cv beat;
    ``get_detector`` is non-blocking, so the demo path degrades to the scripted
    fallback (honestly tagged) if the build is still in flight.  Idempotent and
    safe when weights are absent.
    """
    global _detector_failed
    if _detector is not None or _detector_failed:
        return

    def _build() -> None:
        global _detector, _detector_failed
        if not _detector_lock.acquire(blocking=False):
            return
        try:
            if _detector is None and not _detector_failed:
                from models.cv.inference import CrackDetector
                _detector = CrackDetector(weights_path=WEIGHTS, conf=DETECT_CONF,
                                          iou=DETECT_IOU)
        except Exception as exc:          # pragma: no cover
            log.warning("cv_feed: prebuild failed (%s); scripted fallback", exc)
            _detector_failed = True
        finally:
            _detector_lock.release()

    threading.Thread(target=_build, name="cv-detector-prebuild",
                     daemon=True).start()


def reset_detector() -> None:
    """Drop the cached detector (test seam / source-change reset)."""
    global _detector, _detector_failed
    with _detector_lock:
        _detector = None
        _detector_failed = False


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
        if det is None:
            # PERF-03: model still loading (or build failed) — scripted fallback
            # rather than blocking the fusion thread on the 92 MB load.  The row
            # is tagged honestly; the very next cv beat retries the real model.
            raise RuntimeError("crack model not ready (prebuild in flight or failed)")
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
        # item 18: pixel-scale, UNcalibrated crack width of the TOP detection
        # (mask geometry in px — NEVER mm; requires a calibration target).
        from models.cv.crack_width import crack_pixel_width
        w = crack_pixel_width(top["mask"])
        return {
            "cv": round(cv, 3),
            "conf": round(conf, 3),
            "area_norm": round(area_norm, 5),
            "crack_width_px": w,
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
            "crack_width_px": None,
            "frame": frame_name,
            "model": "scripted-fallback",
            "source": "cv_feed-fallback",
            "mode": "scripted",
            "fallback": True,
            "reason": str(exc),
        }
