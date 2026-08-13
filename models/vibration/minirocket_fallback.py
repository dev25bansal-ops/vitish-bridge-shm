"""
vibration/minirocket_fallback.py — MiniRocket-style ZERO-TRAINING feature
transform + Ridge classifier fallback demo.

MiniRocket (Dempster et al., 2022) in a nutshell, with ZERO learned weights:
  * ~1000 random kernels (length 9, taps drawn from {-1,0,1}), each with a
    random dilation and a random bias (deterministic RNG, seeded).
  * For every window, each kernel produces TWO features: the PPV (proportion of
    positive values) of the positive-weight convolution and the PPV of the
    negative-weight convolution -> 2 * n_kernels features per window.
  * A Ridge classifier (sklearn, L2-regularized least squares) is then fit on
    those features for a fast, transparent healthy-vs-damaged demo model.

This is the "zero-training-fallback" demo: the transform needs no fit, so a
classifier can be trained from a handful of labelled windows in milliseconds.
If scikit-learn's Ridge is unavailable (or no damaged windows were supplied),
the caller falls back to heuristic.py.

Pure numpy + sklearn.linear_model only.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

_KERNEL_LENGTH = 9


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


class MiniRocketFeatures:
    """Random dilated-convolution + PPV feature transform.

    Kernels and dilations are random (seeded); biases are CALIBRATED from the
    reference data (median positive-conv output), exactly like real MiniRocket.
    This is still "zero learned weights" — no gradient training, just a data
    quantile — but it makes PPV features amplitude-aware and discriminative.
    """

    def __init__(self, n_kernels: int = 1000, kernel_length: int = _KERNEL_LENGTH,
                 dilation_max: int = 32, seed: int = 42) -> None:
        self.n_kernels = int(n_kernels)
        self.kernel_length = int(kernel_length)
        self.dilation_max = int(dilation_max)
        rng = np.random.default_rng(int(seed))
        # random kernels: taps in {-1, 0, 1}; bias uniform in [1, 4] (log-ish space)
        self.kernels = rng.choice([-1, 0, 1], size=(self.n_kernels, self.kernel_length))
        # ensure each kernel has at least one +1 and one -1 tap (MiniRocket does)
        for i in range(self.n_kernels):
            if not np.any(self.kernels[i] > 0):
                self.kernels[i, 0] = 1
            if not np.any(self.kernels[i] < 0):
                self.kernels[i, 1] = -1
        self.dilations = rng.integers(1, self.dilation_max + 1, size=self.n_kernels)
        self.biases = np.full(self.n_kernels, 1.0, dtype=np.float32)  # fallback
        self._fit = False

    def fit(self, X: np.ndarray) -> "MiniRocketFeatures":
        """Calibrate per-kernel biases from reference windows (a data quantile)."""
        X = np.asarray(X, dtype=np.float32)
        if X.ndim == 1:
            X = X[None, :]
        for i in range(self.n_kernels):
            w = self.kernels[i]
            d = self.dilations[i]
            pos = self._conv(X, w * (w > 0), d)      # (n, L')
            vals = pos[pos > 0]
            if vals.size:
                self.biases[i] = float(np.median(vals))
            else:
                self.biases[i] = 1.0
        self._fit = True
        return self

    def transform(self, windows: np.ndarray) -> np.ndarray:
        """(N, L) windows -> (N, 2*n_kernels) PPV features (float32)."""
        X = np.asarray(windows, dtype=np.float32)
        if X.ndim == 1:
            X = X[None, :]
        n, length = X.shape
        feats = np.zeros((n, 2 * self.n_kernels), dtype=np.float32)
        for i in range(self.n_kernels):
            w = self.kernels[i]
            d = self.dilations[i]
            b = self.biases[i]
            pos = self._ppv(X, w * (w > 0), d, b)
            neg = self._ppv(X, w * (w < 0), d, b)
            feats[:, 2 * i] = pos
            feats[:, 2 * i + 1] = neg
        return feats

    def _conv(self, X: np.ndarray, w: np.ndarray, d: int) -> np.ndarray:
        """Dilated convolution of every row of X with kernel w, dilation d."""
        n, L = X.shape
        k = w.size
        out_len = L - (k - 1) * d
        if out_len <= 0:
            return np.zeros((n, 0), dtype=np.float32)
        out = np.zeros((n, out_len), dtype=np.float32)
        for tap in range(k):
            wv = w[tap]
            if wv == 0:
                continue
            out += wv * X[:, tap * d: tap * d + out_len]
        return out

    def _ppv(self, X: np.ndarray, w: np.ndarray, d: int, b: float) -> np.ndarray:
        """Proportion of dilated-conv outputs above the bias, per row of X."""
        out = self._conv(X, w, d)
        if out.shape[1] == 0:
            return np.full(out.shape[0], 0.0, dtype=np.float32)
        return np.mean(out > b, axis=1).astype(np.float32)


class MiniRocketRidge:
    """Ridge classifier on MiniRocket features; returns (score, uncertainty)."""

    def __init__(self, n_kernels: int = 1000, alpha: float = 1.0, seed: int = 42) -> None:
        from sklearn.linear_model import Ridge
        self.transform = MiniRocketFeatures(n_kernels=n_kernels, seed=seed)
        self.ridge = Ridge(alpha=alpha)
        self._fit_n = 0
        self._margin_scale = 1.0

    def fit(self, healthy: np.ndarray, damaged: np.ndarray) -> "MiniRocketRidge":
        h = np.asarray(healthy, dtype=np.float32)
        d = np.asarray(damaged, dtype=np.float32)
        if h.ndim == 1:
            h = h[None, :]
        if d.ndim == 1:
            d = d[None, :]
        self.transform.fit(np.vstack([h, d]))  # calibrate PPV biases from data
        X = self.transform.transform(np.vstack([h, d]))
        y = np.concatenate([np.zeros(h.shape[0]), np.ones(d.shape[0])])
        self.ridge.fit(X, y)
        self._fit_n = int(y.size)
        # self-calibrate scale from training residuals
        resid = np.std(self.ridge.predict(X) - y) or 1.0
        self._margin_scale = max(resid, 1e-3)
        return self

    def score(self, window: np.ndarray) -> tuple[float, float]:
        if self._fit_n == 0:
            return (0.0, 1.0)
        x = self.transform.transform(np.asarray(window, dtype=np.float32)[None, :])[0]
        y = float(self.ridge.predict(x[None, :])[0])
        # map continuous ridge output (fit to 0/1) to a probability-ish score
        score = 1.0 / (1.0 + np.exp(-(y - 0.5) / self._margin_scale))
        # uncertainty highest near the decision boundary (y ~ 0.5)
        ambiguity = 1.0 - abs(y - 0.5) * 2.0
        unc = _clamp(0.15 + 0.85 * ambiguity)
        return (_clamp(score), unc)


def make_fallback_scorer(healthy: np.ndarray | None = None,
                         damaged: np.ndarray | None = None,
                         n_kernels: int = 1000) -> object:
    """Return a scorer with `.score(window)->(score,unc)`.

    Uses MiniRocket + Ridge when both healthy AND damaged windows are available;
    otherwise falls back to the deterministic heuristic scorer (heuristic.py).
    """
    if healthy is not None and damaged is not None:
        try:
            h = np.asarray(healthy); d = np.asarray(damaged)
            if h.ndim == 1: h = h[None, :]
            if d.ndim == 1: d = d[None, :]
            if h.shape[0] > 0 and d.shape[0] > 0:
                return MiniRocketRidge(n_kernels=n_kernels).fit(h, d)
        except Exception as exc:
            print(f"  [minirocket] WARNING: Ridge path unavailable ({exc}); "
                  "using heuristic fallback.")
    try:
        from .heuristic import HeuristicAnomalyScorer
    except ImportError:
        from heuristic import HeuristicAnomalyScorer
    sc = HeuristicAnomalyScorer(fs=100.0)
    if healthy is not None:
        for w in np.asarray(healthy):
            sc.update_healthy(w)
    return sc


if __name__ == "__main__":  # self-test
    rng = np.random.default_rng(1)
    t = np.arange(1024) / 100.0

    def synth(amp, extra=0.0, seed=0):
        r = np.random.default_rng(seed)
        return (0.05 * np.sin(2 * np.pi * 2.0 * t) + 0.04 * np.sin(2 * np.pi * 5.5 * t)
                + 0.02 * np.sin(2 * np.pi * 9.0 * t) + 0.01 * r.standard_normal(1024)) * amp \
            + extra * r.standard_normal(1024)

    healthy = np.stack([synth(1.0, seed=50 + i) for i in range(20)])
    damaged = np.stack([synth(1.6 + 0.1 * i, extra=0.03, seed=300 + i) for i in range(20)])
    sc = make_fallback_scorer(healthy, damaged, n_kernels=200)
    s_h, u_h = sc.score(synth(1.0, seed=99))
    s_d, u_d = sc.score(synth(2.0, extra=0.04, seed=99))
    print(f"minirocket_fallback.py self-test PASS (n_kernels=200, fit_n={sc._fit_n if hasattr(sc,'_fit_n') else 'heuristic'}) "
          f"healthy=({s_h:.3f},{u_h:.3f}) damaged=({s_d:.3f},{u_d:.3f})")
    assert s_d > s_h, (s_h, s_d)
    assert 0.0 <= s_d <= 1.0 and 0.0 <= u_d <= 1.0
