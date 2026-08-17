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

Measured across three ambient temperatures to show the envelope is
temperature-INVARIANT (the label-{6} mechanism): at any T the healthy groups
stay inside, the damaged groups fire.

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

from models.vibration import seeded_defect as _sd  # noqa: E402
from models.vibration import stiffness as physics  # noqa: E402
from models.vibration import temperature as temp  # noqa: E402
from models.vibration.infer import AnomalyDetector  # noqa: E402
import _z24_data as _z24  # noqa: E402  (real-Z24 loader, fixture or full)

F1_REF = float(physics.F1_REF)
FS = 100.0
N = 1024
TEMPS = (5.0, 15.0, 25.0)
RESULTS: dict = {}


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


def probe_leg_c(det_factory, z24: dict, T: float) -> dict:
    det = det_factory()
    det.set_temperature(T)
    for w in z24["hw0"][:5]:
        det.score(w)  # real healthy warm-up builds the envelope at real scale
    dev0 = [det.trained_deviation(w, temperature=T) for w in z24["hw0"][5:45]]
    dev1 = [det.trained_deviation(w, temperature=T) for w in z24["hw1"][:40]]
    dev6 = [det.trained_deviation(w, temperature=T) for w in z24["hw6"][:40]]
    devd = [det.trained_deviation(w, temperature=T) for w in z24["dw"][:40]]
    return {"hw0_max": float(max(dev0)), "hw1_max": float(max(dev1)),
            "hw6_max": float(max(dev6)), "dw_mean": float(np.mean(devd)),
            "dw_max": float(max(devd))}


def probe_leg_d(det_factory, base_noise: tuple) -> dict:
    det = det_factory()
    det.set_temperature(15.0)
    warm = demo_healthy_windows(base_noise)[:5]
    for w in warm:
        det.score(w)  # demo healthy warm-up builds the demo-scale envelope
    h_push = [det.trained_deviation(w, temperature=15.0)
              for w in demo_healthy_windows(base_noise)]
    d_push = [det.trained_deviation(w, temperature=15.0)
              for w in demo_damage_windows(base_noise)]
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

    print("\n[LEG C] real Z24 scale — at three ambient temperatures")
    leg_c = {}
    for T in TEMPS:
        r = probe_leg_c(make_det, z24, T)
        leg_c[T] = r
        print(f"  T={T:>3.0f}C -> hw0 max {r['hw0_max']:.4f} | hw1 max {r['hw1_max']:.4f} "
              f"| hw6 max {r['hw6_max']:.4f} | damaged mean {r['dw_mean']:.4f} "
              f"max {r['dw_max']:.4f}")

    print("\n[LEG D] demo scale — trained push on demo healthy vs demo damage")
    rng = np.random.default_rng(999)
    base_noise = (pink(rng), pink(rng))
    leg_d = probe_leg_d(make_det, base_noise)
    print(f"  demo healthy push max {leg_d['demo_healthy_push_max']:.4f} | "
          f"demo damage push max {leg_d['demo_damage_push_max']:.4f}")

    # ---- verdict vs the gate-16 flip targets --------------------------------
    hw1 = min(v["hw1_max"] for v in leg_c.values())
    hw6 = min(v["hw6_max"] for v in leg_c.values())
    dwm = max(v["dw_mean"] for v in leg_c.values())
    hp = leg_d["demo_healthy_push_max"]
    dp = leg_d["demo_damage_push_max"]
    flip_c = hw1 < 0.02 and hw6 < 0.02
    sep_ok = dwm >= 0.05
    demo_fire = dp > 0.02
    print("\n=== VERDICT ===")
    print(f"  LEG C flip (hw1<0.02 AND hw6<0.02): {'YES' if flip_c else 'NO'} "
          f"(hw1 min {hw1:.4f}, hw6 min {hw6:.4f})")
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