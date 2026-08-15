"""Trained-path regression gate — ROADMAP line 56 (relabeled per line 40).

For a long time NO test exercised `_score_vae_ocsvm` / `_score_lstm` /
`trained_deviation` / the backend's `trained_push` path with the SHIPPED
artifacts in models/weights/ — the trained ensemble was an untested black box.

Honesty relabel (decision 2026-08-15, ROADMAP line 40): the shipped scaler.pkl
has a near-zero-variance feature (min scale_ 1.4e-8), so standardized values
explode and the raw trained score saturates to ~0.9743 for healthy AND damaged
windows (measured: raw 0.9743 / 0.9743 / 0.9743 for healthy / damaged /
f1-shift; trained_deviation = push = 0.0 for all three).  The trained ensemble
contributes ZERO separation; the deterministic spectral floor
(backend/app/anomaly.py) carries the demo arc.  Rather than pretend the weights
detect, this gate pins the HONEST relabeled behavior:

  * artifacts load (has_trained_models True) and are labelled EXPERIMENTAL/INERT
  * warm-up returns (0.0, 1.0) and push 0.0
  * trained_deviation(healthy) == trained_deviation(damaged) == 0.0 (inert)
  * the module-level demo_predictor.trained_push the backend actually calls is 0.0
  * the deterministic floor separates healthy vs damaged (arc carried by floor)

A future non-degenerate retrain (ROADMAP line 117) must FLIP
EXPECT_DAMAGED_DEV to a positive bound and assert separation instead — that is
the trained-path gate the retrain item promises.

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

from models.vibration import demo_predictor  # noqa: E402
from models.vibration.infer import AnomalyDetector  # noqa: E402

print("[trained-path] shipped-artifact regression gate (relabeled: ensemble inert)")
print("  EXPECT_DAMAGED_DEV = 0.0  # relabel (degenerate scaler.pkl); "
      "flip to >0 after a non-degenerate retrain (ROADMAP line 117)")

# The relabeled expectation for the damaged-window push: with the shipped
# degenerate scaler the ensemble is inert, so damaged dev must be ~0 (NOT a
# decorative >0).  A real retrain flips this constant.
EXPECT_DAMAGED_DEV = 0.0

_FAILS: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _FAILS.append(name)


# --- deterministic demo-scale windows -----------------------------------------
_FS = 100.0
_T = np.arange(1024) / _FS


def synth(amp: float, extra: float = 0.0, f1: float = 3.8, seed: int = 0) -> np.ndarray:
    r = np.random.default_rng(seed)
    return ((0.05 * np.sin(2 * np.pi * f1 * _T) + 0.03 * np.sin(2 * np.pi * 2.0 * _T)
             + 0.02 * np.sin(2 * np.pi * 5.5 * _T) + 0.01 * r.standard_normal(1024)) * amp
            + extra * r.standard_normal(1024))


WEIGHTS = ROOT / "models" / "weights"
det = AnomalyDetector(weights_dir=WEIGHTS, n_healthy=5)

# --- 1. the real shipped artifacts load, and are honestly labelled -------------
_check("has_trained_models True (artifacts loaded, real path)",
       det.has_trained_models is True, det.mode)
_check("scaler detected degenerate (near-zero-variance feature)",
       det._scaler_degenerate is True)
_check("mode honest: EXPERIMENTAL + INERT label",
       "EXPERIMENTAL" in det.mode and "INERT" in det.mode, det.mode)

# --- 2. warm-up: honest no-evidence (0.0, 1.0), envelope untouched -------------
for i in range(5):
    s, u = det.score(synth(1.0, seed=100 + i))
    _check(f"warmup {i + 1} score (0.0, 1.0)", (s, u) == (0.0, 1.0), f"{s},{u}")
_check("inert ensemble leaves NO trained envelope (floor-only)",
       det._envelope_seen is False and det._envelope_hi == 0.0)

# --- 3. relabeled assertion: trained_deviation is 0 for healthy AND damaged ----
for name, w in (("healthy", synth(1.0, seed=900)),
                ("damaged", synth(1.7, extra=0.02, seed=901)),
                ("f1-shift", synth(1.0, f1=3.24, seed=902))):
    dev = det.trained_deviation(w)
    _check(f"trained_deviation({name}) == {EXPECT_DAMAGED_DEV}",
           abs(dev - EXPECT_DAMAGED_DEV) < 1e-9, f"dev={dev:.6f}")
    _check(f"trained_deviation({name}) bounded [0,1]",
           0.0 <= dev <= 1.0, str(dev))

# --- 4. _score_vae_ocsvm / _trained_raw guards: never score an inert ensemble --
raw, unc = det._trained_raw(synth(1.7, extra=0.02, seed=911))
_check("_trained_raw returns (0.0, 1.0) for inert ensemble",
       raw == 0.0 and unc == 1.0, f"{raw},{unc}")
s, u = det._score_vae_ocsvm(synth(1.7, extra=0.02, seed=912))
_check("_score_vae_ocsvm short-circuits (0.0, 1.0)", s == 0.0 and u == 1.0,
       f"{s},{u}")

# --- 5. the module-level path the BACKEND actually calls (own detector) --------
# demo_predictor.trained_push is what backend/app/anomaly.py calls every window.
for i in range(demo_predictor._N_HEALTHY):
    p = demo_predictor.trained_push(synth(1.0, seed=200 + i))
    _check(f"module warmup {i + 1} push == 0.0", p == 0.0, f"push={p:.6f}")
for name, w in (("healthy", synth(1.0, seed=950)),
                ("damaged", synth(1.7, extra=0.02, seed=951))):
    p = demo_predictor.trained_push(w)
    _check(f"module trained_push({name}) == 0.0", p == 0.0, f"push={p:.6f}")

# --- 6. the deterministic floor carries the arc (separates healthy vs damaged) -
from app.anomaly import get_anomaly, reset_anomaly_baseline  # noqa: E402

reset_anomaly_baseline()
_ = get_anomaly(synth(1.0, seed=700))   # prime the floor baseline
s_h, _ = get_anomaly(synth(1.0, seed=701))
s_d, _ = get_anomaly(synth(1.7, extra=0.02, seed=702))
_check("floor separates healthy < damaged (arc carried by the floor)",
       s_h < s_d, f"healthy={s_h:.3f} damaged={s_d:.3f}")
_check("floor scores bounded [0,1]", 0.0 <= s_h <= 1.0 and 0.0 <= s_d <= 1.0,
       f"{s_h},{s_d}")

# --- 7. reset_baseline restarts warm-up (state hygiene) ------------------------
det.reset_baseline()
_check("reset -> envelope cleared", det._envelope_seen is False)
s, u = det.score(synth(1.0, seed=800))
_check("reset -> warm-up restarts (0.0, 1.0)", (s, u) == (0.0, 1.0), f"{s},{u}")

print("\nRESULT", "FAIL" if _FAILS else "PASS", len(_FAILS), "failures")
sys.exit(1 if _FAILS else 0)
