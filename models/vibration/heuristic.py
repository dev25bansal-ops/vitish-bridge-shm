"""
vibration/heuristic.py — DETERMINISTIC, zero-weights fallback anomaly scorer.

This is the DEMO-CRITICAL path: it must always produce a (score, uncertainty)
for any 1024-sample @100 Hz window even with no trained models on disk.

Method (fully deterministic, self-calibrating):
  1. The first `n_healthy_max` windows fed via `.update_healthy()` build a
     baseline "healthy PSD template" (running mean/std of healthy PSDs) plus a
     baseline RMS distribution.
  2. A current window is scored by its distance to the healthy template:
       * log-spectral distance (LSD) over f >= 0.5 Hz,
       * LSD restricted to the 0.5-10 Hz structural band (bridge modal band),
       * relative RMS deviation vs the healthy baseline.
  3. The healthy windows themselves are used to self-calibrate the mapping
     distance -> score (median healthy distance d_med, scale k = max(d_med, 0.05)),
     so a genuinely healthy window scores near a 0.1-0.2 noise floor and a
     clearly altered spectrum rises toward 1.0.
  4. Uncertainty is composed of (a) baseline maturity (# healthy windows seen),
     (b) spectral entropy of the current window (broadband = ambiguous), and
     (c) template variability.

A clear, labelled answer is returned even with 0 healthy windows:
(0.0, 1.0)  -> "no evidence yet, maximum uncertainty".
"""
from __future__ import annotations

import numpy as np

try:
    from .features import periodogram, rms
except ImportError:  # running as a bare script
    from features import periodogram, rms

_EPS = 1e-12
_MIN_HEALTHY = 3          # minimum baseline windows before scores are meaningful
_SPECTRAL_FLOOR = 0.5     # Hz; ignore sub-Hz (drift/DC leakage) in distances
_HEALTHY_SCORE_FLOOR = 0.12


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


class HeuristicAnomalyScorer:
    """Deterministic spectral + RMS fallback anomaly scorer."""

    def __init__(
        self,
        fs: float = 100.0,
        n_healthy_max: int = 30,
        rms_trigger_rel: float = 0.30,
        rms_trigger_sigma: float = 3.0,
    ) -> None:
        self.fs = float(fs)
        self.n_healthy_max = int(n_healthy_max)
        self.rms_trigger_rel = float(rms_trigger_rel)
        self.rms_trigger_sigma = float(rms_trigger_sigma)
        self._psds: list[np.ndarray] = []
        self._rmss: list[float] = []
        self._template_mean: np.ndarray | None = None
        self._template_std: np.ndarray | None = None
        self._d_med = 0.05
        self._d_scale = 0.10
        self._base_rms = 0.0
        self._base_rms_std = 0.0
        self.n_healthy = 0

    # ------------------------------------------------------------------ build
    def update_healthy(self, window: np.ndarray) -> None:
        """Feed a known-healthy window into the baseline template."""
        window = np.asarray(window, dtype=np.float64).ravel()
        if window.size == 0:
            return
        f, p = periodogram(window, self.fs)
        self._psds.append(p)
        self._rmss.append(rms(window))
        if len(self._psds) > self.n_healthy_max:
            self._psds.pop(0)
            self._rmss.pop(0)
        self.n_healthy = len(self._psds)
        self._rebuild_template()
        # self-calibrate distance scale from the healthy set itself
        if self.n_healthy >= _MIN_HEALTHY:
            d_health = np.array([self._spectral_distance(p) for p in self._psds])
            self._d_med = float(np.median(d_health))
            self._d_scale = max(float(np.std(d_health)) or self._d_med, 0.05)

    def _rebuild_template(self) -> None:
        if not self._psds:
            self._template_mean = self._template_std = None
            return
        stack = np.stack(self._psds, axis=0)
        self._template_mean = stack.mean(axis=0)
        self._template_std = stack.std(axis=0)

    # ------------------------------------------------------------- distances
    def _freq_mask(self, n_bins: int) -> np.ndarray:
        freqs = np.fft.rfftfreq(n_bins, d=1.0 / self.fs)
        return freqs >= _SPECTRAL_FLOOR

    def _spectral_distance(self, psd: np.ndarray) -> float:
        """Combined log-spectral + RMS distance of one PSD to the template."""
        tm = self._template_mean
        if tm is None or tm.shape != psd.shape:
            return 0.0
        mask = self._freq_mask(psd.size)
        if not np.any(mask):
            return 0.0
        logp = np.log(psd[mask] + _EPS)
        logt = np.log(tm[mask] + _EPS)
        diff = logp - logt
        lsd = float(np.sqrt(np.mean(diff ** 2)))
        # structural band 0.5-10 Hz emphasises bridge modal changes
        freqs = np.fft.rfftfreq(psd.size, d=1.0 / self.fs)
        band = (freqs[mask] >= _BAND_LO) & (freqs[mask] <= _BAND_HI)
        low_lsd = float(np.sqrt(np.mean(diff[band] ** 2))) if np.any(band) else lsd
        return 0.55 * lsd + 0.35 * low_lsd

    # ---------------------------------------------------------------- scoring
    def score(self, window: np.ndarray) -> tuple[float, float]:
        """Return (anomaly_score_0_1, uncertainty_0_1) for one window."""
        window = np.asarray(window, dtype=np.float64).ravel()
        if self.n_healthy < _MIN_HEALTHY:
            # Honest: no evidence yet. Score 0 (don't alarm) with max uncertainty.
            return (0.0, 1.0)

        f, p = periodogram(window, self.fs)
        d = self._spectral_distance(p)

        # relative RMS deviation vs healthy baseline
        cur_rms = rms(window)
        base = max(self._base_rms, np.median(self._rmss) if self._rmss else 0.0)
        rms_dev = abs(cur_rms - base) / max(base, _EPS)

        # composite distance, then self-calibrated monotone map
        d = d + 0.6 * min(rms_dev, 2.0)
        excess = d - self._d_med
        k = self._d_scale
        score = _HEALTHY_SCORE_FLOOR + (1.0 - _HEALTHY_SCORE_FLOOR) * (
            excess / (excess + k) if excess > 0 else 0.0
        )

        # uncertainty: baseline maturity + spectral entropy + template variability
        maturity = float(min(1.0, self.n_healthy / 10.0))
        ent = self._spectral_entropy_norm(p)
        tcv = self._template_cv()
        uncertainty = 0.35 * (1.0 - maturity) + 0.35 * ent + 0.2 * tcv + 0.10
        return (_clamp(score), _clamp(uncertainty))

    def rms_flag(self, window: np.ndarray) -> bool:
        """Edge-level RMS anomaly flag (mirrors contract `flag` field)."""
        window = np.asarray(window, dtype=np.float64).ravel()
        if self.n_healthy < _MIN_HEALTHY:
            return False
        base = np.median(self._rmss) if self._rmss else 0.0
        rel = abs(rms(window) - base) / max(base, _EPS)
        return bool(rel > self.rms_trigger_rel or
                    (self._base_rms_std > _EPS and
                     abs(rms(window) - self._base_rms) > self.rms_trigger_sigma * self._base_rms_std))

    # --------------------------------------------------------------- helpers
    def _spectral_entropy_norm(self, psd: np.ndarray) -> float:
        mask = self._freq_mask(psd.size)
        if not np.any(mask):
            return 0.0
        s = psd[mask].sum()
        if s <= _EPS:
            return 0.0
        q = psd[mask] / s
        h = -float(np.sum(q * np.log(q + _EPS)))
        return float(_clamp(h / np.log(q.size), 0.0, 1.0))

    def _template_cv(self) -> float:
        tm, ts = self._template_mean, self._template_std
        if tm is None or ts is None:
            return 0.5
        mask = self._freq_mask(tm.size)
        if not np.any(mask):
            return 0.5
        cv = float(np.nanmean(ts[mask] / (tm[mask] + _EPS)))
        return _clamp(cv / (cv + 1.0), 0.0, 1.0)


_BAND_LO = 0.5
_BAND_HI = 10.0


if __name__ == "__main__":  # self-test / demo
    rng = np.random.default_rng(7)
    fs = 100.0
    t = np.arange(1024) / fs

    def synth_window(amp: float, extra: float = 0.0, seed: int = 0) -> np.ndarray:
        r = np.random.default_rng(seed)
        base = (
            0.05 * np.sin(2 * np.pi * 2.0 * t)
            + 0.04 * np.sin(2 * np.pi * 5.5 * t)
            + 0.02 * np.sin(2 * np.pi * 9.0 * t)
            + 0.01 * r.standard_normal(1024)
        )
        return base * amp + extra * r.standard_normal(1024)

    sc = HeuristicAnomalyScorer(fs=fs)
    for i in range(12):
        sc.update_healthy(synth_window(1.0, seed=10 + i))
    s_h, u_h = sc.score(synth_window(1.0, seed=100))
    s_d, u_d = sc.score(synth_window(1.6, extra=0.02, seed=200))
    print(f"heuristic.py self-test PASS  healthy=(score={s_h:.3f}, unc={u_h:.3f})"
          f"  damaged=(score={s_d:.3f}, unc={u_d:.3f})  rms_flag={sc.rms_flag(synth_window(1.6, seed=3))}")
    assert s_h < 0.35, s_h
    assert s_d > s_h, (s_h, s_d)
    assert 0.0 <= s_d <= 1.0 and 0.0 <= u_d <= 1.0
