"""
VITISH 2026 · PS#99 SHM — vibration anomaly interface.

The rest of the backend calls ONE stable function::

    score, uncertainty = get_anomaly(window, fs=100)

    * window      : numpy array of 1024 accelerations (m/s^2)
    * score       : float in [0, 1], higher = more anomalous
    * uncertainty : float in [0, 1] (band around the anomaly evidence)

When the ML agent ships real weights at ``models/vibration/demo_predictor.py``
exposing the same signature, this module auto-delegates to it.  Until then (or
if that module is missing/broken) a *deterministic spectral heuristic* is used:

  1. 1/f-normalised PSD of the window (0.5-20 Hz band)
  2. features: peak-to-mean "tonality", low-band (2-8 Hz) energy share, RMS
  3. baseline = EMA of features over windows that look healthy (score < 0.35)
  4. score = 1 - exp(-raw), where raw grows with tonality/low-band deviation
     and with RMS exceeding ~1.5x the healthy baseline.

A strong tonal ~4 Hz + harmonics (the synthetic tendon-rupture signature) makes
``tonality`` explode, so the score reliably climbs toward ~0.9 on damage while
hovering near ~0.05-0.15 on healthy traffic.
"""
from __future__ import annotations

import logging
from typing import Tuple

import numpy as np

log = logging.getLogger(__name__)

_BAND_MIN = 0.5
_BAND_MAX = 20.0
_LOW_MIN = 2.0
_LOW_MAX = 8.0
_SCALE_TONALITY = 25.0
_SCALE_LOW_SHARE = 0.30
_RMS_RATIO_KICK = 1.5
_HEALTHY_SCORE_CAP = 0.35
_BASELINE_ALPHA = 0.05

# deterministic per-process baseline (reset-able for tests / live re-fit)
# NOTE (item 11, ROADMAP-NEXT): this is a single PROCESS-GLOBAL envelope shared
# by all three nodes — the healthy reference is calibrated over the whole fleet
# stream, not per node.  That is deliberate (a fleet-wide ambient baseline is
# more stable than three tiny per-node EMAs), and `reset_anomaly_baseline()` is
# the single knob for tests / data-source switches.
_baseline = None  # {"tonality": float, "low_share": float, "rms": float}

# ROADMAP line 68: the floor-vs-trained split of the LAST scored window, so the
# UI can transparently credit whichever detector carries the arc. Informational
# only — never read by the scoring path, so it can never influence the BHI arc.
_last_evidence: dict = {"floor": 0.0, "trained_push": 0.0, "score": 0.0}


def reset_anomaly_baseline() -> None:
    """Clear the healthy reference envelope (used by tests and live re-fit)."""
    global _baseline
    _baseline = None


def last_evidence() -> dict:
    """Copy of the floor-vs-trained split of the last scored window."""
    return dict(_last_evidence)


def _features(arr: np.ndarray, fs: int) -> dict:
    x = arr - float(np.mean(arr))
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    power = np.abs(spec) ** 2
    band = (freqs >= _BAND_MIN) & (freqs <= _BAND_MAX)
    pb, fb = power[band], freqs[band]
    total = float(pb.sum()) + 1e-12
    peak = float(pb.max()) if pb.size else 0.0
    mean = float(pb.mean()) + 1e-12
    tonality = peak / mean
    low = (fb >= _LOW_MIN) & (fb <= _LOW_MAX)
    low_share = float(pb[low].sum() / total) if low.any() else 0.0
    return {
        "tonality": tonality,
        "low_share": low_share,
        "peak_f": float(fb[np.argmax(pb)]) if pb.size else 0.0,
        "rms": float(np.sqrt(np.mean(x ** 2))),
    }


def _score_from_features(feat: dict) -> float:
    global _baseline
    if _baseline is None:
        _baseline = {
            "tonality": feat["tonality"],
            "low_share": feat["low_share"],
            "rms": max(feat["rms"], 1e-9),
        }
    b = _baseline
    d_ton = max(0.0, feat["tonality"] - b["tonality"])
    d_share = max(0.0, feat["low_share"] - b["low_share"])
    r_ratio = feat["rms"] / max(b["rms"], 1e-9)

    raw = 0.55 * (d_ton / _SCALE_TONALITY) + 0.25 * (d_share / _SCALE_LOW_SHARE)
    if r_ratio > _RMS_RATIO_KICK:
        raw += 0.20 * (1.0 - np.exp(-(r_ratio - _RMS_RATIO_KICK)))

    score = float(1.0 - np.exp(-max(raw, 0.0)))

    # only refit the healthy envelope while the window looks healthy — i.e. both
    # low score AND not rms-elevated.  Without the rms gate, a single broadband
    # event (e.g. the demo's tendon-snap burst, rms >> 100x healthy) inflates
    # the baseline so the subsequent real damage signature is read as "normal"
    # for many windows (measured: baseline rms 8.6e-6 -> 5.4e-2 in one window,
    # then the damage score collapses to ~0 until the tonality overcomes it).
    if score < _HEALTHY_SCORE_CAP and r_ratio <= _RMS_RATIO_KICK:
        for k in ("tonality", "low_share", "rms"):
            b[k] = (1.0 - _BASELINE_ALPHA) * b[k] + _BASELINE_ALPHA * feat[k]
    return score


def _spectral_heuristic(window: np.ndarray, fs: int = 100) -> Tuple[float, float]:
    feat = _features(window, fs)
    score = _score_from_features(feat)
    uncertainty = float(min(0.40, 0.03 + 0.28 * score))
    return score, uncertainty


def get_anomaly(window, fs: int = 100) -> Tuple[float, float]:
    """Return (score, uncertainty) for one 1024-sample window.

    THE DEMO-CRITICAL ENTRY POINT.  The deterministic spectral heuristic
    (below) is the ALWAYS-ON floor: it is what makes the GREEN->RED story arc
    work, and it never depends on trained weights.  On top of the floor, the ML
    ensemble (``models/vibration/demo_predictor``) may ADD a trained-model push
    -- but ONLY as its envelope-relative deviation (see demo_predictor), so an
    uninformative or missing model contributes ~0 and can never break the arc.
    Currently (ROADMAP line 40 relabel) the shipped trained ensemble is
    EXPERIMENTAL and INERT — its scaler is degenerate, so `trained_push` is
    0.0 and this floor alone carries the demo arc.
    """
    arr = np.asarray(window, dtype=np.float64).reshape(-1)
    if arr.size < 64:
        return 0.0, 0.05

    base_score, base_unc = _spectral_heuristic(arr, fs)

    push = 0.0
    try:
        from models.vibration import demo_predictor  # type: ignore[import-not-found]
        # trained_push is documented as returning [0, 1] (envelope-relative
        # deviation); item 11 enforces the bound so a buggy model can never pull
        # the floor score negative or past 1.0.
        push = float(np.clip(float(demo_predictor.trained_push(arr, fs=fs)), 0.0, 1.0))
    except Exception as exc:  # pragma: no cover - depends on models agent
        log.debug("trained push unavailable, floor only (%s)", exc)

    score = float(np.clip(base_score + push, 0.0, 1.0))
    uncertainty = float(np.clip(base_unc + 0.20 * push, 0.0, 0.40))
    # ROADMAP line 68: record the floor vs trained split for the UI. Written
    # AFTER scoring, so this bookkeeping cannot perturb the arc.
    global _last_evidence
    _last_evidence = {"floor": round(base_score, 4),
                      "trained_push": round(push, 4),
                      "score": round(score, 4)}
    return score, uncertainty
