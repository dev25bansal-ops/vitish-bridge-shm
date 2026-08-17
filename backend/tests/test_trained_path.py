"""Trained-path regression gate — FLIPPED to separation (PostHackathon §117).

Previously this gate pinned the INERT relabel: the shipped scaler.pkl had a
near-zero-variance feature (min scale_ 1.4e-8), so standardized values exploded
and the VAE/OCSVM scored ~0.9743 for healthy AND damaged (trained_deviation =
push = 0.0 for all three).  The trained ensemble contributed ZERO separation and
was honestly declared INERT — the deterministic spectral floor owned the arc.

2026-08-15: real retrain on real Z24 (data/z24/inputs.npy, healthy labels
{0,1,6}, channels 6/7/8) with the scale-clamped training code
(models/vibration/train_vae_ocsvm.py clamps scaler.scale_ to >= 1e-6) produced a
NON-degenerate scaler.  Measured on shipped state (this gate's premise):

    trained_deviation  healthy label-0  mean 0.0000  max 0.0000  (real Z24)
    trained_deviation  damaged (labels 2-16, excl. 6)  mean 0.0579  (fixture)
    healthy labels 1 and 6 are documented STATE-CONFOUNDS that deviate like
        damage (max ~0.31 / ~0.37): the envelope is state-specific — this is
        pinned, not hidden, in test_deconfounding.py LEG C
    demo-scale synthetic stream (RMS ~0.05): dev 0.0 for healthy AND damaged
        -> the healthy-envelope absorbs the amplitude domain shift -> the pinned
        demo arc is preserved (verify_demo_arc.py: 19/19, unchanged 87.1/65.7/34.9)

So the INERT banner is removed: the trained path contributes real separation on
shipped state — measured, not assumed.  This gate now asserts:

  * artifacts load, the scaler is NON-degenerate, mode says envelope-floor+push
  * real healthy-vs-damaged separation on real Z24 — from the committed
    fixture (data/z24/fixture/) on a fresh clone/CI, or the full benchmark
    when present (PostHackathon TEST-F3: no silent SKIP on CI)
  * the trained path never short-circuits (raw scores are real, not (0.0, 1.0))
  * on the demo-scale stream the trained push stays ~0 (arc cannot be broken)
  * the deterministic floor still separates healthy < damaged

The trained weights and a real-Z24 fixture are COMMITTED, so on a fresh
clone/CI this gate exercises the real trained path and real benchmark evidence.
If both are somehow absent it SKIPS with exit 0 and prints why.

Run:  python backend/tests/test_trained_path.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
for _p in (BACKEND, ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np  # noqa: E402

import _z24_data as _z24  # noqa: E402  (shared real-Z24 loader, fixture-or-full)

from models.vibration.infer import AnomalyDetector  # noqa: E402

WEIGHTS = ROOT / "models" / "weights"

# The flipped expectation: a non-degenerate retrain (PostHackathon §117) must
# give the damaged-window trained deviation a real positive mean.  Measured on
# shipped state: label-2-alone mean 0.1158 (full) / damaged-group 0.0579
# (fixture, labels 2-16 excl. 6); the bound keeps headroom.
EXPECT_DAMAGED_DEV = 0.05

_FAILS: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _FAILS.append(name)


# --- skip guard: weights are COMMITTED (PostHackathon TEST-F3) ------------------
# models/weights/vae.pt + ocsvm.pkl are tracked, so a fresh clone / CI has them.
# Only skip (exit 0, honestly) if they are genuinely absent (untracked dev build).
if not ((WEIGHTS / "vae.pt").exists() and (WEIGHTS / "ocsvm.pkl").exists()):
    print("[trained-path] trained weights absent (models/weights/* missing; "
          "untracked build) -> SKIP.  Retrain on a machine with the weights:\n"
          "    python models/vibration/train_vae_ocsvm.py --data data/z24/inputs.npy"
          " --mode features --epochs 60\n"
          "    python models/vibration/train_lstm_ae.py --data data/z24/inputs.npy"
          " --epochs 30")
    print("\nRESULT SKIP (no weights)")
    sys.exit(0)

print("[trained-path] shipped-artifact regression gate (flipped: separation)")
print("  EXPECT_DAMAGED_DEV >= 0.05  # non-degenerate retrain (PostHackathon §117)")

# The ensemble scores with MC-dropout (stochastic by design, for uncertainty).
# A regression gate must be reproducible, so every detector block re-seeds torch
# + numpy to the same state -> identical dropout draws on every run.
import torch  # noqa: E402


def _seed(s: int = 0) -> None:
    torch.manual_seed(s)
    np.random.seed(s)


_seed()

# --- deterministic demo-scale windows (arc-preservation + floor checks) ---------
_FS = 100.0
_T = np.arange(1024) / _FS


def synth(amp: float, extra: float = 0.0, f1: float = 3.8, seed: int = 0) -> np.ndarray:
    r = np.random.default_rng(seed)
    return ((0.05 * np.sin(2 * np.pi * f1 * _T) + 0.03 * np.sin(2 * np.pi * 2.0 * _T)
             + 0.02 * np.sin(2 * np.pi * 5.5 * _T) + 0.01 * r.standard_normal(1024)) * amp
            + extra * r.standard_normal(1024))


# --- real Z24 evidence comes from the shared loader (fixture or full) ----------
z24 = _z24.load_windows()

det = AnomalyDetector(weights_dir=WEIGHTS, n_healthy=5)

# --- 1. artifacts load, NON-degenerate, honest mode -----------------------------
_check("has_trained_models True (artifacts loaded, real path)",
       det.has_trained_models is True, det.mode)
_check("scaler NON-degenerate (retrained, min scale_ >= 1e-6)",
       det._scaler_degenerate is False)
_check("mode: envelope-floor+push, no INERT label",
       "envelope-floor+push" in det.mode and "INERT" not in det.mode, det.mode)

# --- 2. warm-up: honest no-evidence (0.0, 1.0) ----------------------------------
for i in range(5):
    s, u = det.score(synth(1.0, seed=100 + i))
    _check(f"warmup {i + 1} score (0.0, 1.0)", (s, u) == (0.0, 1.0), f"{s},{u}")
_check("envelope built from healthy demo windows (trained raw measured)",
       det._envelope_seen is True, str(det._envelope_seen))

# --- 3. trained path never short-circuits (raw scores are real) -----------------
raw, unc = det._trained_raw(synth(1.7, extra=0.02, seed=911))
_check("_trained_raw real, not the (0.0, 1.0) inert sentinel",
       raw > 0.0 and raw < 1.0 and unc > 0.0, f"{raw:.4f},{unc:.4f}")
s, u = det._score_vae_ocsvm(synth(1.7, extra=0.02, seed=912))
_check("_score_vae_ocsvm active (not the inert sentinel)",
       s > 0.0 and s < 1.0 and u > 0.0, f"{s:.4f},{u:.4f}")

# --- 4. REAL separation on real Z24 (fixture or full data) ----------------------
if z24["present"]:
    print(f"    TRAINED_REAL_DATA=RUN({z24['source']})")
    _seed()
    det2 = AnomalyDetector(weights_dir=WEIGHTS, n_healthy=5)
    for w in z24["hw0"][:5]:
        det2.score(w)  # real healthy warm-up builds the envelope at real scale
    dev0 = [det2.trained_deviation(w) for w in z24["hw0"][5:45]]
    dev_d = [det2.trained_deviation(w) for w in z24["dw"][:40]]
    _check("real healthy label-0 dev stays ~0 (the envelope's own state)",
           max(dev0) < 0.02, f"max={max(dev0):.4f}")
    _check(f"real damaged dev mean >= {EXPECT_DAMAGED_DEV} (separation)",
           float(np.mean(dev_d)) >= EXPECT_DAMAGED_DEV, f"mean={np.mean(dev_d):.4f}")
    _check("real damaged dev exceeds healthy label-0 dev",
           max(dev_d) > max(dev0), f"damaged={max(dev_d):.4f} label0={max(dev0):.4f}")
    print(f"    measured: label-0 dev mean {np.mean(dev0):.4f} max {max(dev0):.4f} | "
          f"damaged dev mean {np.mean(dev_d):.4f} max {max(dev_d):.4f}")
else:
    print("    TRAINED_REAL_DATA=SKIP")
    print("    real Z24 absent (data/z24/inputs.npy and data/z24/fixture/ both "
          "missing) -> the real-data separation assertions cannot run")

# --- 5. demo-scale stream: trained push stays ~0 (arc cannot be broken) ---------
_seed()
det3 = AnomalyDetector(weights_dir=WEIGHTS, n_healthy=5)
for i in range(5):
    det3.score(synth(1.0, seed=200 + i))
dev_h = [det3.trained_deviation(synth(1.0, seed=300 + i)) for i in range(6)]
dev_d = [det3.trained_deviation(synth(1.7, extra=0.02, seed=400 + i)) for i in range(6)]
_check("demo-scale trained push stays ~0 (envelope absorbs the amplitude shift; "
       "the trained path cannot break the pinned arc)",
       max(dev_h + dev_d) < 0.02, f"max={max(dev_h + dev_d):.4f}")

# --- 6. module-level path the BACKEND actually calls (own detector) -------------
from models.vibration import demo_predictor  # noqa: E402
if z24["present"]:
    _seed()  # deterministic dropout draws for the lazily-created module detector
    for w in z24["hw0"][:5]:
        demo_predictor.trained_push(w)  # warm-up on real healthy
    push_h = [demo_predictor.trained_push(w) for w in z24["hw0"][5:45]]
    push_d = [demo_predictor.trained_push(w) for w in z24["dw"][:40]]
    _check("module trained_push: real damaged mean > real healthy mean "
           "(the backend's own path separates)",
           float(np.mean(push_d)) > float(np.mean(push_h)),
           f"healthy={np.mean(push_h):.4f} damaged={np.mean(push_d):.4f}")
    _check("module trained_push bounded [0,1]",
           0.0 <= float(np.min(push_h + push_d)) and float(np.max(push_h + push_d)) <= 1.0,
           f"max={np.max(push_h + push_d):.4f}")

# --- 7. the deterministic floor carries the arc (healthy < damaged) -------------
from app.anomaly import get_anomaly, reset_anomaly_baseline  # noqa: E402

reset_anomaly_baseline()
_ = get_anomaly(synth(1.0, seed=700))   # prime the floor baseline
s_h, _ = get_anomaly(synth(1.0, seed=701))
s_d, _ = get_anomaly(synth(1.7, extra=0.02, seed=702))
_check("floor separates healthy < damaged (arc carried by the floor)",
       s_h < s_d, f"healthy={s_h:.3f} damaged={s_d:.3f}")
_check("floor scores bounded [0,1]", 0.0 <= s_h <= 1.0 and 0.0 <= s_d <= 1.0,
       f"{s_h},{s_d}")

# --- 8. reset_baseline restarts warm-up (state hygiene) -------------------------
det.reset_baseline()
_check("reset -> envelope cleared", det._envelope_seen is False)
s, u = det.score(synth(1.0, seed=800))
_check("reset -> warm-up restarts (0.0, 1.0)", (s, u) == (0.0, 1.0), f"{s},{u}")

print("\nRESULT", "FAIL" if _FAILS else "PASS", len(_FAILS), "failures")
sys.exit(1 if _FAILS else 0)
