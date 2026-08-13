"""
models — ML package for VITISH-2026 bridge SHM.

Single entry point used by the backend:
    from models import load_predictor
    vib = load_predictor("vibration")     # -> AnomalyDetector  (.score(window)->(0..1,0..1))
    cv  = load_predictor("crack")         # -> CrackDetector    (.detect(image_bgr)->list[dict])

Both predictors load trained weights from models/weights/ when present and fall
back to deterministic heuristics otherwise, so every demo path works with ZERO
trained weights.

Sub-packages:
    vibration/   VAE/OCSVM + LSTM-AE anomaly detection, heuristic fallback,
                 MiniRocket+Ridge fallback, feature extraction
    cv/          YOLO-seg crack detection, Canny/contour heuristic fallback,
                 dataset prep (SDNET2018 / Ultralytics crack-seg / synthetic)
    fusion/      auditable BHI = 100*(1 - 0.40*cv - 0.35*vib - 0.25*load)
"""
from __future__ import annotations

__version__ = "0.1.0"

_PREDICTOR_KINDS = ("vibration", "crack")


def load_predictor(kind: str):
    """Instantiate the requested predictor, preferring trained weights.

    kind: "vibration" -> vibration.infer.AnomalyDetector
          "crack"     -> cv.inference.CrackDetector
    """
    if kind == "vibration":
        from .vibration.infer import AnomalyDetector
        return AnomalyDetector()
    if kind == "crack":
        from .cv.inference import CrackDetector
        return CrackDetector()
    raise ValueError(f"unknown predictor {kind!r}; choose from {_PREDICTOR_KINDS}")


__all__ = ["load_predictor", "__version__"]
