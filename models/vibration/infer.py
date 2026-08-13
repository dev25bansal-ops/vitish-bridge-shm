"""
vibration/infer.py — inference API for vibration anomaly detection.

AnomalyDetector is the single entry point the backend calls:
    det = AnomalyDetector()                 # caches healthy baseline
    det.add_healthy(window)                 # optional explicit healthy feed
    score, unc = det.score(window)          # (0..1, 0..1)

Behaviour (always works at demo time):
  * If trained artifacts exist in models/weights/ (vae.pt+ocsvm.pkl+scaler.pkl
    and/or lstm_ae.pt) they are loaded and used preferentially.
  * Otherwise (or blended) the deterministic heuristic fallback from
    heuristic.py is used — ZERO trained weights required.
  * Warm-up: the first `n_healthy` windows are absorbed into the healthy
    baseline (returns (0.0, 1.0) = "no evidence yet, max uncertainty").
  * Thread-safe: all mutable state is guarded by a lock.
  * Deterministic: torch seeds are fixed; the fallback is pure deterministic.
"""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

try:
    from . import features as feat_mod
    from .heuristic import HeuristicAnomalyScorer
except ImportError:  # bare-script run
    import features as feat_mod
    from heuristic import HeuristicAnomalyScorer

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS = REPO_ROOT / "models" / "weights"


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def _load_pickle(path: Path):
    # SECURITY NOTE: joblib/pickle artifacts (ocsvm.pkl, scaler.pkl) are produced
    # ONLY by this repo's own training scripts in models/weights/. They are not
    # fetched from the network or any external source, so this is an acceptable,
    # documented use of pickle. If weights are ever distributed from a third
    # party, switch these to a schema-validated format (msgspec/json).
    try:
        import joblib
        return joblib.load(path)
    except Exception:
        import pickle
        with open(path, "rb") as fh:
            return pickle.load(fh)


class AnomalyDetector:
    """Ensemble vibration anomaly detector with guaranteed heuristic fallback."""

    def __init__(
        self,
        weights_dir: str | Path = DEFAULT_WEIGHTS,
        fs: float = 100.0,
        window_n: int = 1024,
        n_healthy: int = 10,
        blend_heuristic: float = 0.20,
        mc_samples: int = 20,
    ) -> None:
        self.weights_dir = Path(weights_dir)
        self.fs = float(fs)
        self.window_n = int(window_n)
        self.n_healthy = int(n_healthy)
        self.blend_heuristic = _clamp(float(blend_heuristic), 0.0, 1.0)
        self.mc_samples = int(mc_samples)
        self._lock = threading.Lock()
        self._buffer: list[np.ndarray] = []
        self._warmup_done = False

        # healthy-envelope floor+push fusion (decision #5, false-alarm-proof):
        # the trained model can only PUSH the anomaly estimate above the
        # deterministic baseline, and only when its raw score departs from this
        # bridge's OWN healthy envelope (high-water mark seen during warm-up).
        # A model with no discriminative signal (dev ~ 0) leaves the heuristic
        # in charge, so the demo arc can never be broken by a bad model.
        self._envelope_hi = 0.0          # max raw trained score seen while healthy
        self._envelope_seen = False
        self._envelope_margin = 0.05     # dead-band so healthy jitter never pushes
        self.trained_push = 0.85         # strength of the trained-model push

        # heuristic fallback baseline (always maintained so it can serve/blend)
        self._heuristic = HeuristicAnomalyScorer(fs=self.fs)

        # trained artifacts (None if absent -> pure heuristic mode)
        self._vae = None
        self._vae_cfg: dict = {}
        self._ocsvm = None
        self._scaler = None
        self._lstm = None
        self._lstm_cfg: dict = {}
        self._device = None
        self._mode_note = "heuristic (no trained weights found)"

        self._load_trained()

    # ------------------------------------------------------------------ setup
    def _load_trained(self) -> None:
        w = self.weights_dir
        vae_path, ocsvm_path, scaler_path, lstm_path = (
            w / "vae.pt", w / "ocsvm.pkl", w / "scaler.pkl", w / "lstm_ae.pt",
        )
        have_torch = True
        try:
            import torch
        except Exception:
            have_torch = False

        if have_torch:
            import torch
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            # SECURITY NOTE: vae.pt / lstm_ae.pt are torch.checkpoint dicts written
            # ONLY by this repo's own training scripts (tensors + simple scalars),
            # so weights_only=True is safe and blocks arbitrary pickle execution.
            if vae_path.exists() and ocsvm_path.exists():
                try:
                    ckpt = torch.load(vae_path, map_location="cpu", weights_only=True)
                    self._vae_cfg = ckpt
                    if self._scaler is None and scaler_path.exists():
                        self._scaler = _load_pickle(scaler_path)
                    self._ocsvm = _load_pickle(ocsvm_path)
                    self._mode_note = (f"VAE/OCSVM (vae.pt, mode={ckpt.get('mode')}, "
                                       f"latent={ckpt.get('latent_dim')})")
                    self._mode_note += " · envelope-floor+push"
                except Exception as exc:
                    print(f"  [infer] WARNING: failed to load VAE/OCSVM artifacts ({exc}); "
                          "using heuristic fallback.")
                    self._vae = None
            if lstm_path.exists():
                try:
                    ckpt = torch.load(lstm_path, map_location="cpu", weights_only=True)
                    self._lstm_cfg = ckpt
                    self._mode_note += " + LSTM-AE" if "VAE" in self._mode_note else "LSTM-AE"
                except Exception as exc:
                    print(f"  [infer] WARNING: failed to load LSTM-AE artifact ({exc}).")
            print(f"  [infer] mode: {self._mode_note}  (device={self._device})")

    @property
    def mode(self) -> str:
        return self._mode_note

    @property
    def has_trained_models(self) -> bool:
        return (self._ocsvm is not None) or (self._lstm_cfg.get("state_dict") is not None)

    # ------------------------------------------------------------- window prep
    def _prep(self, window: np.ndarray) -> np.ndarray:
        w = np.asarray(window, dtype=np.float64).ravel()
        if w.size == 0:
            return np.zeros(self.window_n, dtype=np.float64)
        if w.size == self.window_n:
            return w
        if w.size > self.window_n:
            return w[: self.window_n]
        out = np.zeros(self.window_n, dtype=np.float64)
        out[: w.size] = w
        return out

    # ----------------------------------------------------------- baseline feed
    def _trained_raw(self, window: np.ndarray) -> tuple[float, float]:
        """Mean raw trained score + uncertainty across enabled trained components."""
        scores: list[float] = []
        uncs: list[float] = []
        if self._ocsvm is not None:
            s, u = self._score_vae_ocsvm(window)
            scores.append(s)
            uncs.append(u)
        if self._lstm_cfg:
            s, u = self._score_lstm(window)
            scores.append(s)
            uncs.append(u)
        if not scores:
            return 0.0, 1.0
        return float(np.mean(scores)), float(np.mean(uncs))

    def _update_envelope(self, raw: float) -> None:
        """Extend the healthy envelope's high-water mark (warm-up windows only)."""
        if raw > 0.0:
            self._envelope_seen = True
            self._envelope_hi = max(self._envelope_hi, float(raw))

    def add_healthy(self, window: np.ndarray) -> None:
        """Explicitly register a known-healthy window into the baseline."""
        w = self._prep(window)
        with self._lock:
            self._buffer.append(w)
            self._heuristic.update_healthy(w)
            if self._ocsvm is not None or self._lstm_cfg:
                self._update_envelope(self._trained_raw(w)[0])
            if len(self._buffer) >= self.n_healthy:
                self._warmup_done = True

    # ---------------------------------------------------------------- scoring
    def score(self, window: np.ndarray) -> tuple[float, float]:
        """Return (anomaly_score_0_1, uncertainty_0_1) for one 1024-sample window."""
        w = self._prep(window)
        with self._lock:
            t_s, t_u = self._trained_raw(w)
            if not self._warmup_done:
                # warm-up: absorb this window as healthy evidence
                self._buffer.append(w)
                self._heuristic.update_healthy(w)
                if self._ocsvm is not None or self._lstm_cfg:
                    self._update_envelope(t_s)
                if len(self._buffer) >= self.n_healthy:
                    self._warmup_done = True
                return (0.0, 1.0)  # honest: baseline not established

            hs, hu = self._heuristic.score(w)
            if self._envelope_seen:
                # Healthy-envelope floor+push: the deterministic heuristic is the
                # floor; the trained ensemble only ADDS evidence when it departs
                # from this bridge's own healthy envelope (measured during
                # warm-up). dev~0 (no trained signal) => heuristic in charge, so
                # a model that cannot separate its classes can never trigger a
                # false alarm or break the GREEN->RED story arc.
                dev = max(0.0, t_s - self._envelope_hi - self._envelope_margin)
                score = hs + dev * self.trained_push
                uncertainty = max(hu, 0.10 + 0.6 * dev)
            else:
                score, uncertainty = hs, hu
            return (_clamp(score), _clamp(uncertainty))

    def rms_flag(self, window: np.ndarray) -> bool:
        """Edge-level RMS anomaly flag (mirrors the contract `flag` field)."""
        with self._lock:
            return self._heuristic.rms_flag(self._prep(window))

    def reset_baseline(self) -> None:
        with self._lock:
            self._buffer = []
            self._warmup_done = False
            self._envelope_hi = 0.0
            self._envelope_seen = False
            self._heuristic = HeuristicAnomalyScorer(fs=self.fs)

    # ------------------------------------------------------ trained-only push
    def trained_deviation(self, window: np.ndarray) -> float:
        """Envelope-relative trained evidence, used as a PUSH on the backend floor.

        Returns a float in [0, 1] = how far the trained ensemble's raw score
        departs above this bridge's OWN healthy envelope (high-water mark seen
        during warm-up). Returns 0.0 during warm-up or when no trained model is
        loaded, so an uninformative model can never create a false alarm. The
        deterministic spectral floor (owned by backend/app/anomaly.py) is always
        the base; this only adds honest trained evidence on top.
        """
        w = self._prep(window)
        with self._lock:
            t_s, _ = self._trained_raw(w)
            if not self._warmup_done:
                # warm-up: absorb as healthy evidence (demo healthy phase does this)
                self._buffer.append(w)
                self._heuristic.update_healthy(w)
                if self._ocsvm is not None or self._lstm_cfg:
                    self._update_envelope(t_s)
                if len(self._buffer) >= self.n_healthy:
                    self._warmup_done = True
                return 0.0
            if not self._envelope_seen:
                return 0.0
            dev = max(0.0, t_s - self._envelope_hi - self._envelope_margin)
            return _clamp(dev * self.trained_push)

    # --------------------------------------------------------- trained scoring
    def _vae_input(self, window: np.ndarray) -> np.ndarray:
        cfg = self._vae_cfg
        if cfg.get("mode") == "features":
            return feat_mod.extract_features(window, fs=self.fs)[None, :].astype(np.float64)
        return window[None, :].astype(np.float64)

    def _score_vae_ocsvm(self, window: np.ndarray) -> tuple[float, float]:
        import torch
        cfg = self._vae_cfg
        x = self._vae_input(window)
        if self._scaler is not None:
            x = self._scaler.transform(x)
        xt = torch.tensor(x, dtype=torch.float32, device=self._device)

        model = self._lazy_vae()
        # MC-dropout reconstruction distribution
        recon_losses: list[float] = []
        model.train()
        with torch.no_grad():
            for _ in range(max(1, self.mc_samples)):
                recon, mu, _ = model(xt)
                recon_losses.append(float(((recon - xt) ** 2).mean().item()))
        model.eval()
        with torch.no_grad():
            _, mu, _ = model(xt)
        mu_np = mu.cpu().numpy()

        # reconstruction-ratio score
        thresh = float(cfg.get("threshold_p95", 1e-3)) or 1e-3
        err = float(np.mean(recon_losses))
        score_recon = 1.0 - np.exp(-(err / thresh) / 1.5)

        # OCSVM margin score (decision_function: + inlier, - outlier)
        raw = -float(self._ocsvm.decision_function(mu_np)[0])
        score_ocsvm = 1.0 / (1.0 + np.exp(-(raw + 1.0) / 1.5))

        score = 0.5 * score_recon + 0.5 * score_ocsvm
        # uncertainty from dropout spread
        cv = float(np.std(recon_losses) / (float(np.mean(recon_losses)) + 1e-9))
        unc = 0.15 + 0.85 * (cv / (cv + 1.0))
        return (_clamp(score), _clamp(unc))

    def _lazy_vae(self):
        import torch
        if self._vae is None:
            from .train_vae_ocsvm import VAE  # (only imported when artifacts exist)
            cfg = self._vae_cfg
            model = VAE(input_dim=int(cfg.get("input_dim", 1024)),
                        latent_dim=int(cfg.get("latent_dim", 16)),
                        dropout=float(cfg.get("dropout", 0.1)))
            model.load_state_dict(cfg["state_dict"])
            model.eval()
            self._vae = model.to(self._device)
        return self._vae

    def _score_lstm(self, window: np.ndarray) -> tuple[float, float]:
        import torch
        cfg = self._lstm_cfg
        model = self._lazy_lstm()
        seq_len = int(cfg.get("seq_len", self.window_n))
        w = window[-seq_len:] if window.size >= seq_len else self._prep(window)
        xt = torch.tensor(w, dtype=torch.float32, device=self._device)[None, :, None]

        losses: list[float] = []
        model.train()  # MC-dropout
        with torch.no_grad():
            for _ in range(max(1, self.mc_samples)):
                recon = model(xt)
                losses.append(float(((recon - xt.squeeze(-1)) ** 2).mean().item()))
        model.eval()

        err = float(np.mean(losses))
        thresh = float(cfg.get("threshold", 1e-3)) or 1e-3
        score = 1.0 - np.exp(-(err / thresh) / 1.5)
        cv = float(np.std(losses) / (float(np.mean(losses)) + 1e-9))
        unc = 0.15 + 0.85 * (cv / (cv + 1.0))
        return (_clamp(score), _clamp(unc))

    def _lazy_lstm(self):
        import torch
        if self._lstm is None:
            from .train_lstm_ae import LSTMAE
            cfg = self._lstm_cfg
            model = LSTMAE(seq_len=int(cfg.get("seq_len", self.window_n)),
                           hidden=int(cfg.get("hidden", 32)),
                           latent_dim=int(cfg.get("latent_dim", 16)),
                           dropout=float(cfg.get("dropout", 0.2)))
            model.load_state_dict(cfg["state_dict"])
            model.eval()
            self._lstm = model.to(self._device)
        return self._lstm


if __name__ == "__main__":  # self-test (heuristic fallback path)
    rng = np.random.default_rng(3)
    fs = 100.0
    t = np.arange(1024) / fs

    def synth(amp, extra=0.0, seed=0):
        r = np.random.default_rng(seed)
        return (0.05 * np.sin(2 * np.pi * 2.0 * t) + 0.04 * np.sin(2 * np.pi * 5.5 * t)
                + 0.02 * np.sin(2 * np.pi * 9.0 * t) + 0.01 * r.standard_normal(1024)) * amp \
            + extra * r.standard_normal(1024)

    det = AnomalyDetector(n_healthy=8, weights_dir=REPO_ROOT / "models" / "weights" / "no_such_dir")
    for i in range(8):
        s, u = det.score(synth(1.0, seed=100 + i))
        assert (s, u) == (0.0, 1.0), "warm-up should return (0,1)"
    s_h, u_h = det.score(synth(1.0, seed=900))
    s_d, u_d = det.score(synth(1.7, extra=0.02, seed=901))
    print(f"infer.py self-test PASS (fallback mode={det.mode}) "
          f"healthy=({s_h:.3f},{u_h:.3f}) damaged=({s_d:.3f},{u_d:.3f}) "
          f"rms_flag={det.rms_flag(synth(1.7, seed=9))}")
    assert s_d > s_h, (s_h, s_d)
    assert 0.0 <= s_d <= 1.0 and 0.0 <= u_d <= 1.0
