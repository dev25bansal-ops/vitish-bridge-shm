"""
vibration/features.py — window-to-feature extraction for structural vibration.

Input contract (see backend/app/contract.py): windows of 1024 samples @ 100 Hz
(WINDOW_N = FS_ACCEL * WINDOW_S). This module is PURE numpy — no torch, no
scipy, no sklearn — so it is guaranteed importable and fast.

Extracted features (7-dim):
    0. rms                  root-mean-square acceleration (m/s^2)
    1. peak_freq            frequency (Hz) of max PSD excluding DC
    2. spectral_centroid    power-weighted mean frequency (Hz)
    3. band_power_0_5_10    PSD integral over the 0.5-10 Hz band (structural band)
    4. spectral_entropy     normalized entropy of the PSD (0..1)
    5. one_over_f_slope     slope of log PSD vs log f fitted over [1, min(25, fs/4)] Hz
    6. temperature          covariate, default 0.0 (passes through, not estimated)

Every value is deterministic given the window.
"""
from __future__ import annotations

import numpy as np

FEATURE_NAMES: list[str] = [
    "rms",
    "peak_freq",
    "spectral_centroid",
    "band_power_0_5_10",
    "spectral_entropy",
    "one_over_f_slope",
    "temperature",
]
N_FEATURES = len(FEATURE_NAMES)

_EPS = 1e-12
_BAND_LO = 0.5
_BAND_HI = 10.0


def periodogram(x: np.ndarray, fs: float = 100.0) -> tuple[np.ndarray, np.ndarray]:
    """Hann-windowed one-sided PSD via numpy FFT.

    Returns (freqs, psd) with units of (m/s^2)^2 / Hz. Pure numpy.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    n = x.size
    if n == 0:
        return np.zeros(0), np.zeros(0)
    x = x - x.mean()                      # remove DC (constant detrend)
    win = np.hanning(n)
    xw = x * win
    X = np.fft.rfft(xw)
    # Normalize so that the integral of PSD over f equals the windowed variance.
    psd = (np.abs(X) ** 2) / (fs * np.sum(win ** 2))
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    return freqs, psd


def rms(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0


def _peak_freq(f: np.ndarray, p: np.ndarray) -> float:
    if f.size < 2:
        return 0.0
    # exclude DC
    nz = f > _EPS
    if not np.any(nz):
        return 0.0
    return float(f[nz][np.argmax(p[nz])])


def _spectral_centroid(f: np.ndarray, p: np.ndarray) -> float:
    denom = p.sum()
    if denom <= _EPS:
        return 0.0
    return float((f * p).sum() / denom)


def _band_power(f: np.ndarray, p: np.ndarray, lo: float = _BAND_LO, hi: float = _BAND_HI) -> float:
    m = (f >= lo) & (f <= hi)
    if not np.any(m):
        return 0.0
    # approximate integral with trapezoid over the selected band
    fsel, psel = f[m], p[m]
    return float(np.trapezoid(psel, fsel)) if fsel.size >= 2 else float(psel[0])


def _spectral_entropy(p: np.ndarray) -> float:
    # normalized Shannon entropy of the PSD (DC excluded)
    if p.size < 2:
        return 0.0
    pz = p[1:] if p[0] > p[1:].max() else p  # drop DC unless negligible
    s = pz.sum()
    if s <= _EPS:
        return 0.0
    q = pz / s
    h = float(-np.sum(q * np.log(q + _EPS)))
    return float(np.clip(h / np.log(q.size), 0.0, 1.0))


def _one_over_f_slope(f: np.ndarray, p: np.ndarray, fs: float) -> float:
    hi = min(25.0, fs / 4.0)
    m = (f >= 1.0) & (f <= hi)
    if np.sum(m) < 3:
        return 0.0
    lf = np.log(f[m] + _EPS)
    lp = np.log(p[m] + _EPS)
    if np.allclose(lf, lf[0]):
        return 0.0
    return float(np.polyfit(lf, lp, 1)[0])


def extract_features(
    window: np.ndarray,
    fs: float = 100.0,
    temperature: float | None = None,
) -> np.ndarray:
    """Return the 7-dim feature vector for one window."""
    window = np.asarray(window, dtype=np.float64).ravel()
    f, p = periodogram(window, fs=fs)
    feat = np.zeros(N_FEATURES, dtype=np.float64)
    feat[0] = rms(window)
    feat[1] = _peak_freq(f, p)
    feat[2] = _spectral_centroid(f, p)
    feat[3] = _band_power(f, p)
    feat[4] = _spectral_entropy(p)
    feat[5] = _one_over_f_slope(f, p, fs)
    feat[6] = float(temperature) if temperature is not None else 0.0
    return feat


def extract_feature_dict(
    window: np.ndarray,
    fs: float = 100.0,
    temperature: float | None = None,
) -> dict[str, float]:
    """Human-readable dict form (useful for logging / audit trail)."""
    v = extract_features(window, fs=fs, temperature=temperature)
    return {name: float(val) for name, val in zip(FEATURE_NAMES, v)}


if __name__ == "__main__":  # self-test
    rng = np.random.default_rng(0)
    fs = 100.0
    t = np.arange(1024) / fs
    healthy = (
        0.05 * np.sin(2 * np.pi * 2.0 * t)
        + 0.04 * np.sin(2 * np.pi * 5.5 * t)
        + 0.02 * np.sin(2 * np.pi * 9.0 * t)
        + 0.01 * rng.standard_normal(1024)
    )
    f, p = periodogram(healthy, fs)
    assert abs(p[0]) < 1e-9, "DC removed"
    v = extract_features(healthy, fs=fs, temperature=21.5)
    assert v.shape == (N_FEATURES,)
    assert v[0] > 0.04, v[0]                 # rms ≈ sqrt((0.05^2+0.04^2+0.02^2)/2 + 0.01^2)
    assert 1.0 <= v[1] <= 12.0, v[1]         # peak in structural band
    assert v[4] >= 0.0 and v[4] <= 1.0       # normalized entropy
    assert v[6] == 21.5
    d = extract_feature_dict(healthy, fs=fs)
    print("features.py self-test PASS:", {k: round(x, 4) for k, x in d.items()})
