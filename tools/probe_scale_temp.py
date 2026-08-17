"""
tools/probe_scale_temp.py — measure the item-17 LEG C/D bounds against a
weights dir (the gate-16 assertions in backend/tests/test_deconfounding.py).

Mirrors test_deconfounding LEG C (real Z24 at real scale) and LEG D (demo
scale), but parameterized by a weights_dir so the decision gate can compare
candidate vs shipped before installing.  Reports the five numbers the gate
flips on:

  LEG C (real Z24):  hw0 max dev  (< 0.02)   hw1 max dev (flip: < 0.02)
                     hw6 max dev (flip: < 0.02)   damaged mean (>= 0.05)
  LEG D (demo):      demo-healthy push (~0)       demo-damaged push (flip: > 0.02)

item-17 conditioning: every window is scored at its OWN IMPLIED temperature —
invert the thermal f1 model f1(T)=f1_ref*(1-ALPHA*(T-20)) for the window's
measured peak frequency (clamped to the training T_GRID).  The coordinated
"temperature-diagonal" envelope is trained on {(spectrum at f1(T), T)} — the
thin healthy curve — so a window must be queried at the T whose thermal f1
matches its spectrum.  Healthy windows (on the seasonal curve) land on the
diagonal and stay inside at any season; damaged windows (f1 below the entire
seasonal band) sit off the diagonal at every implied T and fire.  The measured
+14.6% rupture → implied T ≈ 45 C → clamps to the grid edge (35 C), where the
diagonal f1 is still 6.5% above the rupture's (deliberately) off-curve.

Usage:
  python tools/probe_scale_temp.py --weights models/weights             # shipped
  python tools/probe_scale_temp.py --weights models/weights_scale_temp  # candidate
  python tools/probe_scale_temp.py --weights <dir> --quick              # fixture only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for _p in (ROOT, BACKEND, BACKEND / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from models.vibration import features as feat_mod  # noqa: E402
from models.vibration import seeded_defect as _sd  # noqa: E402
from models.vibration import stiffness as physics  # noqa: E402
from models.vibration import temperature as temp  # noqa: E402
from models.vibration.infer import AnomalyDetector  # noqa: E402
import _z24_data as _z24  # noqa: E402  (real-Z24 loader, fixture or full)

F1_REF = float(physics.F1_REF)
FS = 100.0
N = 1024
# Mirror the retrain's coordinated grid (tools/retrain_scale_temp.py T_GRID).
T_GRID = (-5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0)
RESULT_TEMPS: list[float] = []
RESULTS: dict = {}


def implied_temperature_c(window: np.ndarray) -> float:
    """Invert f1(T) for the window's measured peak frequency, clamped to
    T_GRID.  A healthy window's implied T is the ambient it 'should' be at;
    a damaged window (f1 below the whole seasonal band) saturates at the hot
    grid edge, where its spectrum is still off the diagonal."""
    f1 = float(feat_mod.extract_features(window, fs=FS)[1])
    if not np.isfinite(f1) or f1 <= 0.0:
        return temp.T_REF_C
    t = temp.T_REF_C + (1.0 - f1 / F1_REF) / temp.ALPHA_PER_C
    return float(np.clip(t, min(T_GRID), max(T_GRID)))


def pink(rng: np.random.Generator) -> np.ndarray:
    freqs = np.fft.rfftfreq(N)
    amps = np.empty(len(freqs)); amps[0] = 0.0
    amps[1:] = 1.0 / np.sqrt(np.maximum(freqs[1:], 1e-9))
    spec = rng.standard_normal(len(freqs)) + 1j * rng.standard_normal(len(freqs))
    spec[0] = 0.0
    return np.fft.irfft(spec * amps, N) / (np.std(np.fft.irfft(spec * amps, N)) + 1e-12)


def seasonal_f1(doy: float) -> float:
    return temp.expected_f1(F1_REF, temp.seasonal_temp_c(doy))


def demo_healthy_windows(base_noise: tuple, seed0: int = 0) -> list[np.ndarray]:
    t = np.arange(N) / FS
    out = []
    for doy in (15, 105, 205, 300, 315):
        f1 = seasonal_f1(doy)
        for i in range(6):
            rng = np.random.default_rng(seed0 + i + int(doy))
            ph = rng.uniform(0.0, 2.0 * np.pi)
            res = (np.sin(2 * np.pi * f1 * t + ph)
                   + 0.5 * np.sin(4 * np.pi * f1 * t + 2 * ph)) / 1.12
            out.append(base_noise[0] * 0.6 * 0.05 + base_noise[1] * 0.05 + 0.015 * res)
    return out


def demo_damage_windows(base_noise: tuple, seed0: int = 10) -> list[np.ndarray]:
    f1_dmg = _sd.f1_of_progress(_sd.progress_from_alpha(1.0))
    t = np.arange(N) / FS
    out = []
    for i in range(6):
        sig = (np.sin(2 * np.pi * f1_dmg * t)
               + 0.5 * np.sin(4 * np.pi * f1_dmg * t)
               + (1 / 3) * np.sin(6 * np.pi * f1_dmg * t)) / 1.75
        out.append(base_noise[0] * 0.6 * 0.05 + base_noise[1] * 0.05 + 0.55 * sig)
    return out


def probe_leg_c(det_factory, z24: dict) -> dict:
    det = det_factory()
    for w in z24["hw0"][:5]:
        det.set_temperature(implied_temperature_c(w))  # warm-up in ITS season
        det.score(w)
    dev0 = [det.trained_deviation(w, temperature=implied_temperature_c(w))
            for w in z24["hw0"][5:45]]
    dev1 = [det.trained_deviation(w, temperature=implied_temperature_c(w))
            for w in z24["hw1"][:40]]
    dev6 = [det.trained_deviation(w, temperature=implied_temperature_c(w))
            for w in z24["hw6"][:40]]
    devd = [det.trained_deviation(w, temperature=implied_temperature_c(w))
            for w in z24["dw"][:40]]
    RESULT_TEMPS.extend(implied_temperature_c(w) for w in z24["hw0"][:40])
    RESULT_TEMPS.extend(implied_temperature_c(w) for w in z24["hw1"][:40])
    RESULT_TEMPS.extend(implied_temperature_c(w) for w in z24["hw6"][:40])
    RESULT_TEMPS.extend(implied_temperature_c(w) for w in z24["dw"][:40])
    return {"hw0_max": float(max(dev0)), "hw1_max": float(max(dev1)),
            "hw6_max": float(max(dev6)), "dw_mean": float(np.mean(devd)),
            "dw_max": float(max(devd))}


def probe_leg_d(det_factory, base_noise: tuple) -> dict:
    det = det_factory()
    healthy = demo_healthy_windows(base_noise)
    for w in healthy[:5]:
        det.set_temperature(implied_temperature_c(w))  # demo-healthy warm-up
        det.score(w)
    h_push = [det.trained_deviation(w, temperature=implied_temperature_c(w))
              for w in healthy]
    d_push = [det.trained_deviation(w, temperature=implied_temperature_c(w))
              for w in demo_damage_windows(base_noise)]
    RESULT_TEMPS.extend(implied_temperature_c(w) for w in healthy)
    RESULT_TEMPS.extend(implied_temperature_c(w) for w in demo_damage_windows(base_noise))
    return {"demo_healthy_push_max": float(max(h_push)),
            "demo_damage_push_max": float(max(d_push))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", default=str(ROOT / "models" / "weights"))
    ap.add_argument("--quick", action="store_true", help="fixture-scale Z24 only")
    args = ap.parse_args()
    weights = Path(args.weights)
    print(f"[probe] weights dir: {weights}")

    def make_det() -> AnomalyDetector:
        return AnomalyDetector(weights_dir=weights, n_healthy=5)

    z24 = _z24.load_windows()
    if not z24["present"]:
        print("  no Z24 data present; cannot run LEG C")
        sys.exit(2)
    print(f"  Z24 source: {z24['source']}  hw0={len(z24['hw0'])} hw1={len(z24['hw1'])} "
          f"hw6={len(z24['hw6'])} dw={len(z24['dw'])}")

    print("\n[LEG C] real Z24 scale — every window at its IMPLIED temperature")
    leg_c = probe_leg_c(make_det, z24)
    print(f"  hw0 max {leg_c['hw0_max']:.4f} | hw1 max {leg_c['hw1_max']:.4f} "
          f"| hw6 max {leg_c['hw6_max']:.4f} | damaged mean {leg_c['dw_mean']:.4f} "
          f"max {leg_c['dw_max']:.4f}")

    print("\n[LEG D] demo scale — trained push on demo healthy vs demo damage")
    rng = np.random.default_rng(999)
    base_noise = (pink(rng), pink(rng))
    leg_d = probe_leg_d(make_det, base_noise)
    print(f"  demo healthy push max {leg_d['demo_healthy_push_max']:.4f} | "
          f"demo damage push max {leg_d['demo_damage_push_max']:.4f}")

    temps = np.asarray(RESULT_TEMPS)
    if temps.size:
        print(f"  implied-T distribution: min {temps.min():.1f} p50 {np.median(temps):.1f} "
              f"max {temps.max():.1f} C")

    # ---- verdict vs the gate-16 flip targets --------------------------------
    hw1 = leg_c["hw1_max"]
    hw6 = leg_c["hw6_max"]
    dwm = leg_c["dw_mean"]
    hp = leg_d["demo_healthy_push_max"]
    dp = leg_d["demo_damage_push_max"]
    flip_c = hw1 < 0.02 and hw6 < 0.02
    sep_ok = dwm >= 0.05
    demo_fire = dp > 0.02
    print("\n=== VERDICT ===")
    print(f"  LEG C flip (hw1<0.02 AND hw6<0.02): {'YES' if flip_c else 'NO'} "
          f"(hw1 {hw1:.4f}, hw6 {hw6:.4f})")
    print(f"  damaged separates (mean>=0.05): {'YES' if sep_ok else 'NO'} (mean {dwm:.4f})")
    print(f"  LEG D scale-fire (damage push>0.02): {'YES' if demo_fire else 'NO'} "
          f"(damage {dp:.4f})")
    print(f"  demo healthy stays quiet (push<0.02): {'YES' if hp < 0.02 else 'NO'} "
          f"(push {hp:.4f})")
    RESULTS.update({"leg_c": leg_c, "leg_d": leg_d,
                    "flip_c": flip_c, "sep_ok": sep_ok, "demo_fire": demo_fire,
                    "demo_healthy_quiet": hp < 0.02})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())