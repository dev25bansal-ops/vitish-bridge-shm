"""
models — ML package for VITISH-2026 bridge SHM.

Predictor factory (canonical for scripts and tests):
    from models import load_predictor
    vib = load_predictor("vibration")     # -> AnomalyDetector  (.score(window)->(0..1,0..1))
    cv  = load_predictor("crack")         # -> CrackDetector    (.detect(image_bgr)->list[dict])

load_predictor is MEMOIZED — one instance per kind is created on first call and
shared by every later caller (weights load once per process), and it raises on
unknown kinds.  ROADMAP line 67: the running backend does NOT route through this
module — the vibration detector is reached via models.vibration.demo_predictor
(backend/app/anomaly.py) and the crack detector is cached process-wide by
backend/app/cv_feed.get_detector().  This factory is the honest convenience API
for scripts/tests that want a weights-preferred predictor without wiring the
backend's own caches.

Both predictors load trained weights from models/weights/ when present and fall
back to deterministic heuristics otherwise, so every demo path works with ZERO
trained weights.

Sub-packages:
    vibration/   VAE/OCSVM + LSTM-AE anomaly detection, heuristic fallback,
                 MiniRocket+Ridge fallback, feature extraction
    cv/          YOLO-seg crack detection, Canny/contour heuristic fallback,
                 dataset prep (SDNET2018 / Ultralytics crack-seg / synthetic)
    fusion/      auditable BHI = 100*(1 - 0.40*cv - 0.35*vib - 0.25*load).  The
                 backend fuses via backend/app/contract.compute_bhi (single
                 source of truth); models/fusion holds the standalone reference
                 (bhi.py) and the regulator condition-card mapping (condition.py).
"""
from __future__ import annotations

__version__ = "0.1.0"

_PREDICTOR_KINDS = ("vibration", "crack")

# ROADMAP line 67: instance cache — repeated load_predictor(kind) calls share one
# detector instead of rebuilding (and re-loading weights) per call.
_CACHE: dict[str, object] = {}


def load_predictor(kind: str):
    """Return the MEMOIZED predictor for ``kind`` (weights preferred, heuristic
    fallback otherwise). One instance per kind, shared across all callers.

    kind: "vibration" -> vibration.infer.AnomalyDetector
          "crack"     -> cv.inference.CrackDetector
    """
    if kind not in _CACHE:
        if kind == "vibration":
            from .vibration.infer import AnomalyDetector
            _CACHE[kind] = AnomalyDetector()
        elif kind == "crack":
            from .cv.inference import CrackDetector
            _CACHE[kind] = CrackDetector()
        else:
            raise ValueError(f"unknown predictor {kind!r}; choose from {_PREDICTOR_KINDS}")
    return _CACHE[kind]


def _clear_predictor_cache() -> None:
    """Test hook (ROADMAP line 58 hygiene): drop cached instances so tests are
    order-independent. Not part of the public API."""
    _CACHE.clear()


__all__ = ["load_predictor", "__version__"]
