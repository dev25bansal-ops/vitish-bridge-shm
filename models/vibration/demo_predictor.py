"""
vibration/demo_predictor.py — trained-evidence PUSH for the backend floor.

The backend (``backend/app/anomaly.py``) owns the deterministic spectral floor
(the always-on, false-alarm-proof baseline detector that carries the demo) and
asks this module for ONE thing — how much extra "trained evidence" the ML
ensemble (VAE/OCSVM, LSTM-AE, MiniRocket) contributes for a window:

    push = demo_predictor.trained_push(window, fs=100)   # float in [0, 1]

Honesty + safety rules:
  * ``push`` is the trained ensemble's score measured relative to THIS bridge's
    OWN healthy envelope (high-water mark seen during warm-up), so a model with
    no discriminative signal returns ~0 and can never create a false alarm or
    break the GREEN->RED story arc.  The floor always remains the base.
  * On shipped state (2026-08-15) the ensemble is ACTIVE and separates on real
    Z24: the retrain clamped scaler.scale_ to >= 1e-6 and re-trained on real
    data, so damaged-window trained deviation is ~0.09-0.12 mean (healthy ~0,
    measured).  The demo-scale synthetic stream stays inside the healthy
    envelope, so push stays ~0 during the demo and the pinned arc is preserved.
  * The degenerate-scaler guard (ROADMAP line 40) remains: if a future scaler
    has a near-zero-variance feature, the ensemble is declared INERT and this
    module returns 0.0 rather than falsely scoring.
  * ``push == 0.0`` during warm-up (the first ``n_healthy`` windows are absorbed
    as healthy evidence) and when no trained artifacts exist in models/weights/.
  * Trained artifacts are loaded lazily on first call and cached for the process
    lifetime; a broken/corrupt artifact degrades to push=0, never a crash.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import numpy as np

_detector: Optional["AnomalyDetector"] = None
_detector_failed = False
_build_lock = threading.Lock()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_WEIGHTS = _REPO_ROOT / "models" / "weights"

# 5 windows × 1024 samples @ 100 Hz ≈ 51 s of simulated time at the demo's
# default --rate 1.0 (wall-clock scales with --rate, e.g. ~15 s at rate 3.4).
# Completes during the healthy phase of the 175 s story, well before the ~75 s
# damage onset, so the envelope is built from genuinely healthy windows.
_N_HEALTHY = 5


def _build_detector():
    try:  # package context (backend imports models.vibration.demo_predictor)
        from .infer import AnomalyDetector
    except ImportError:  # bare-script run (python models/vibration/demo_predictor.py)
        from infer import AnomalyDetector
    return AnomalyDetector(weights_dir=_DEFAULT_WEIGHTS, n_healthy=_N_HEALTHY)


def prebuild_detector() -> None:
    """Eagerly build the trained detector on a background thread (PERF-01).

    The FIRST ``trained_push`` used to build the detector inline — torch.load +
    joblib, measured ~2.1s on CUDA / ~1s CPU — a stall that hit the first
    anomaly push (the fusion thread scoring the first windows).  Startup now
    kicks this off in a daemon thread so the model is warm before scoring
    matters.  ``trained_push`` never blocks on the prebuild: it takes the same
    lock non-blocking and returns 0.0 (honest: trained evidence not ready yet)
    if the build is still in flight — the deterministic floor carries those
    windows.  Idempotent + safe when weights are absent (a failure latches
    ``_detector_failed`` exactly like the inline path).
    """
    if _detector is not None or _detector_failed:
        return

    def _build() -> None:
        global _detector, _detector_failed
        if not _build_lock.acquire(blocking=False):
            return
        try:
            if _detector is None and not _detector_failed:
                _detector = _build_detector()
        except Exception as exc:  # pragma: no cover - only when models/ is broken
            import logging
            logging.getLogger(__name__).warning(
                "demo_predictor: prebuild failed (%s); trained push disabled", exc)
            _detector_failed = True
        finally:
            _build_lock.release()

    threading.Thread(target=_build, name="trained-detector-prebuild",
                     daemon=True).start()


def trained_push(window, fs: int = 100, temperature: float | None = None) -> float:
    """Return the trained ensemble's envelope-relative evidence, float in [0,1].

    ``temperature`` (optional °C) is forwarded to the features-mode VAE/OCSVM
    covariate; the backend passes the current site temperature so the envelope
    reads the season correctly (item 17).
    """
    global _detector, _detector_failed
    if _detector is None and not _detector_failed:
        # Non-blocking: if a prebuild is already in flight, skip this window
        # rather than stalling the scoring thread (PERF-01 — the old inline
        # build was a multi-second first-call stall).
        if _build_lock.acquire(blocking=False):
            try:
                if _detector is None and not _detector_failed:
                    _detector = _build_detector()
            except Exception as exc:  # pragma: no cover - only when models/ is broken
                import logging
                logging.getLogger(__name__).warning(
                    "demo_predictor: detector init failed (%s); trained push disabled", exc)
                _detector_failed = True
            finally:
                _build_lock.release()
        else:
            return 0.0
    if _detector is None:
        return 0.0
    try:
        return _detector.trained_deviation(np.asarray(window, dtype=np.float64),
                                           temperature=temperature)
    except Exception:  # pragma: no cover - trained scoring must never break the floor
        return 0.0


if __name__ == "__main__":  # self-test
    fs = 100.0
    t = np.arange(1024) / fs
    rng = np.random.default_rng(3)

    def synth(amp, extra=0.0):
        return (0.05 * np.sin(2 * np.pi * 2.0 * t) + 0.04 * np.sin(2 * np.pi * 5.5 * t)
                + 0.02 * np.sin(2 * np.pi * 9.0 * t) + 0.01 * rng.standard_normal(1024)) * amp \
            + extra * rng.standard_normal(1024)

    det = _build_detector()
    print(f"mode: {det.mode}")
    for _ in range(_N_HEALTHY):
        trained_push(synth(1.0))           # warm-up: push 0
    p_h = trained_push(synth(1.0))
    p_d = trained_push(synth(1.7, extra=0.02))
    print(f"demo_predictor self-test PASS  healthy_push={p_h:.3f} damage_push={p_d:.3f}")
    assert 0.0 <= p_h <= 1.0 and 0.0 <= p_d <= 1.0
