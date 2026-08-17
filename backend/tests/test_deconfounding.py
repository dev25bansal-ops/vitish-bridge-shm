"""Environmental de-confounding gate — temperature-only must NOT false-alarm,
damage must fire (PostHackathon §117, environmental de-confounding study).

The Z24 benchmark's first vertical frequency wanders ~14% peak-to-peak over a
year with air temperature — thermal wandering is the #1 false-damage source in
vibration-based SHM because it can look exactly like stiffness loss.  This gate
pins the measured de-confounding evidence on the SHIPPED detector state:

  LEG A  deterministic spectral floor, seasonal f1 sweep on a FIXED pink-noise
         realization (the ONLY varying quantity is temperature/f1): max floor
         score stays < 0.20 at every season (GREEN — no thermal false alarm).
  LEG B  the SAME floor fires on the seeded rupture at both seasonal extremes
         (> 0.5) — flat-on-temperature-only is separation, not blindness.
  LEG C  trained ensemble at REAL Z24 scale (runs on the full benchmark OR the
         committed fixture data/z24/fixture/ — TEST-F3, never silently skips):
         healthy label {0} (the envelope's own state) stays ~0; damaged
         separates (mean >= 0.05); and TWO documented healthy-state confounds
         are pinned — labels {1} and {6} deviate (max >= 0.02), so the trained
         envelope is NOT state-agnostic (a state-agnostic retrain must bring
         these below 0.02, at which point these assertions flip to that bound).
  LEG D  trained ensemble at DEMO scale: the raw score is amplitude-saturated
         (constant ~0.98 for healthy AND damage), so the envelope makes the
         trained push ~0 for everything — the demo arc is carried by the
         deterministic floor alone (this is why the retrain could not break the
         pinned arc).

The gate asserts the SYSTEM claim (floor flat on temperature-only, fires on
damage — the demo is floor-carried) and documents the trained path's measured
limits honestly.  Deterministic: fixed noise realization + seeded torch/numpy.

Run:  python backend/tests/test_deconfounding.py
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

from models.vibration import temperature as temp  # noqa: E402
from models.vibration import stiffness as physics  # noqa: E402
from models.vibration import seeded_defect as _sd  # noqa: E402
from models.vibration.infer import AnomalyDetector  # noqa: E402

WEIGHTS = ROOT / "models" / "weights"
FS = 100.0
N = 1024
F1_REF = physics.F1_REF

# measured headroom (probe 2026-08-15): floor max across seasons 0.044;
# damage fires 0.720 / 0.939.  Bounds keep honest headroom.
FLOOR_SEASONAL_CAP = 0.20        # < 0.35 healthy cap, 4.5x the measured 0.044
FLOOR_DAMAGE_MIN = 0.50          # fires (measured 0.72-0.94)
# Real-Z24 trained legs: bounds measured on BOTH the full benchmark and the
# committed fixture (data/z24/fixture/, a deterministic real-Z24 sample).
TRAINED_HEALTHY0_DEV_MAX = 0.02  # healthy label {0} (envelope's state) ~0 (measured 0.0000)
TRAINED_DAMAGED_DEV_MIN = 0.05   # damaged separates (full-data label-2 mean 0.1158; fixture 0.058)
TRAINED_HEALTHY1_DEV_MIN = 0.02  # documented confound: healthy label {1} deviates (full 0.2925, fixture 0.3063)
TRAINED_LABEL6_DEV_MIN = 0.02    # documented confound: healthy label {6} deviates (measured max 0.3715)
DEMO_SCALE_PUSH_MAX = 0.02       # demo-scale push ~0 for healthy AND damage

_PASS = 0
_FAILS: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    global _PASS
    if cond:
        _PASS += 1
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _FAILS.append(name)


def _seed(s: int = 0) -> None:
    import torch
    torch.manual_seed(s)
    np.random.seed(s)


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    freqs = np.fft.rfftfreq(n)
    amps = np.empty(len(freqs)); amps[0] = 0.0
    amps[1:] = 1.0 / np.sqrt(np.maximum(freqs[1:], 1e-9))
    spec = rng.standard_normal(len(freqs)) + 1j * rng.standard_normal(len(freqs))
    spec[0] = 0.0
    x = np.fft.irfft(spec * amps, n)
    return x / (np.std(x) + 1e-12)


def seasonal_f1(doy: float) -> float:
    return temp.expected_f1(F1_REF, temp.seasonal_temp_c(doy))


def thermal_windows(doy: float, base_noise: tuple, seed0: int = 0) -> list:
    """Same pink-noise realization at the thermal f1 of `doy` — the ONLY
    difference between seasons is f1 (temperature).  Demo-scale RMS ~0.05."""
    t = np.arange(N) / FS
    out = []
    for i in range(6):
        rng = np.random.default_rng(seed0 + i)
        ph = rng.uniform(0.0, 2.0 * np.pi)
        res = (np.sin(2 * np.pi * seasonal_f1(doy) * t + ph)
               + 0.5 * np.sin(4 * np.pi * seasonal_f1(doy) * t + 2 * ph)) / 1.12
        out.append(base_noise[0] * 0.6 * 0.05 + base_noise[1] * 0.05 + 0.015 * res)
    return out


def damage_windows(base_noise: tuple, seed0: int = 10, f1: float | None = None) -> list:
    """Demo damage form: pink base + strong standing-wave resonance at the
    (optionally season-scaled) seeded-defect f1, amp = rms_damage 0.55."""
    t = np.arange(N) / FS
    if f1 is None:
        f1 = _sd.f1_of_progress(_sd.progress_from_alpha(1.0))
    out = []
    for i in range(6):
        sig = (np.sin(2 * np.pi * f1 * t)
               + 0.5 * np.sin(4 * np.pi * f1 * t)
               + (1 / 3) * np.sin(6 * np.pi * f1 * t)) / 1.75
        out.append(base_noise[0] * 0.6 * 0.05 + base_noise[1] * 0.05 + 0.55 * sig)
    return out


def main() -> int:
    print("[deconfounding] environmental de-confounding on SHIPPED detector "
          "state (temperature-only must stay flat, damage must fire)")
    print(f"  seasonal f1: winter {seasonal_f1(15):.3f} Hz "
          f"(T {temp.seasonal_temp_c(15):.1f}C) -> summer {seasonal_f1(205):.3f} Hz "
          f"(T {temp.seasonal_temp_c(205):.1f}C), p2p "
          f"{100.0 * (seasonal_f1(15) / seasonal_f1(205) - 1.0):.1f}%")
    f1_dmg = _sd.f1_of_progress(_sd.progress_from_alpha(1.0))
    print(f"  seeded rupture f1 {f1_dmg:.3f} Hz "
          f"({100.0 * (f1_dmg / F1_REF - 1.0):.2f}% vs ref, outside the "
          f"+/-{temp.residual_band_pct():.0f}% thermal band)")

    # fixed pink-noise realization: the only independent variable is f1 (season)
    rng = np.random.default_rng(999)
    base_noise = (pink_noise(N, rng), pink_noise(N, rng))

    # ---- LEG A: floor flat on temperature-only (fixed-noise seasonal sweep) --
    from app.anomaly import get_anomaly, reset_anomaly_baseline  # noqa: E402
    print("\n[leg A] deterministic floor — seasonal f1 sweep, FIXED noise")
    reset_anomaly_baseline()
    prime = [thermal_windows(315, base_noise, seed0=20)[i % 6] for i in range(40)]
    for w in prime:
        get_anomaly(w)  # realistic long healthy prime at the campaign start
    floor_scores: dict[str, float] = {}
    for name, doy in [("winter", 15), ("spring", 105), ("summer", 205),
                      ("autumn", 300), ("campaign-start", 315)]:
        s = max(get_anomaly(w)[0] for w in thermal_windows(doy, base_noise, seed0=0))
        floor_scores[name] = s
        _check(f"floor {name} stays GREEN (< {FLOOR_SEASONAL_CAP})", s < FLOOR_SEASONAL_CAP,
               f"{s:.3f}")
    sweep_max = max(floor_scores.values())
    _check("floor across the FULL-year sweep stays GREEN",
           sweep_max < FLOOR_SEASONAL_CAP, f"{sweep_max:.3f}")
    print(f"    measured max/season: {', '.join(f'{k} {v:.3f}' for k, v in floor_scores.items())}")

    # ---- LEG B: floor fires on damage at both seasonal extremes --------------
    print("[leg B] deterministic floor — fires on the seeded rupture")
    reset_anomaly_baseline()
    for w in prime:
        get_anomaly(w)
    d_win = max(get_anomaly(w)[0] for w in
                damage_windows(base_noise, seed0=10, f1=seasonal_f1(15) * (f1_dmg / F1_REF)))
    d_sum = max(get_anomaly(w)[0] for w in
                damage_windows(base_noise, seed0=11, f1=seasonal_f1(205) * (f1_dmg / F1_REF)))
    _check(f"floor fires on rupture@winter (> {FLOOR_DAMAGE_MIN})", d_win > FLOOR_DAMAGE_MIN,
           f"{d_win:.3f}")
    _check(f"floor fires on rupture@summer (> {FLOOR_DAMAGE_MIN})", d_sum > FLOOR_DAMAGE_MIN,
           f"{d_sum:.3f}")
    print(f"    measured: rupture@winter {d_win:.3f} | rupture@summer {d_sum:.3f}")

    # ---- LEG C: trained ensemble at REAL Z24 scale (fixture or full data) ----
    HAS_TRAINED = bool((WEIGHTS / "vae.pt").exists() and (WEIGHTS / "ocsvm.pkl").exists())
    print("[leg C] trained ensemble — REAL Z24 scale")
    if HAS_TRAINED:
        z24 = _z24.load_windows()
        if z24["present"]:
            src = z24["source"]
            print(f"    TRAINED_REAL_DATA=RUN({src})")
            _seed()
            det = AnomalyDetector(weights_dir=WEIGHTS, n_healthy=5)
            for w in z24["hw0"][:5]:
                det.score(w)  # real healthy warm-up builds the envelope at real scale
            dev0 = [det.trained_deviation(w) for w in z24["hw0"][5:45]]
            dev1 = [det.trained_deviation(w) for w in z24["hw1"][:40]]
            dev6 = [det.trained_deviation(w) for w in z24["hw6"][:40]]
            dev_d = [det.trained_deviation(w) for w in z24["dw"][:40]]
            _check(f"real healthy label {{0}} (envelope's own state) dev stays ~0 "
                   f"(< {TRAINED_HEALTHY0_DEV_MAX})",
                   max(dev0) < TRAINED_HEALTHY0_DEV_MAX, f"max={max(dev0):.4f}")
            _check(f"real damaged dev mean >= {TRAINED_DAMAGED_DEV_MIN} (separates)",
                   float(np.mean(dev_d)) >= TRAINED_DAMAGED_DEV_MIN,
                   f"mean={np.mean(dev_d):.4f}")
            # the HONEST findings, pinned so they cannot silently change: the
            # trained envelope is NOT state-agnostic — later-campaign healthy
            # labels {1} and {6} deviate like damage (measured max ~0.31 / ~0.37).
            # A state-agnostic retrain must bring both below
            # TRAINED_HEALTHY0_DEV_MAX (then THESE assertions flip to that bound).
            _check("documented confound: healthy label {1} deviates (>= 0.02)",
                   max(dev1) >= TRAINED_HEALTHY1_DEV_MIN, f"max={max(dev1):.4f}")
            _check("documented confound: healthy label {6} deviates (>= 0.02)",
                   max(dev6) >= TRAINED_LABEL6_DEV_MIN, f"max={max(dev6):.4f}")
            print(f"    measured: label{{0}} max {max(dev0):.4f} | label{{1}} "
                  f"max {max(dev1):.4f} | label{{6}} max {max(dev6):.4f} | "
                  f"damaged mean {np.mean(dev_d):.4f} max {max(dev_d):.4f}")
        else:
            print("    TRAINED_REAL_DATA=SKIP")
            print("    real Z24 absent (data/z24/inputs.npy and data/z24/fixture/ "
                  "both missing) -> trained leg skipped (floor legs above run)")
    else:
        print("    trained weights absent (models/weights/* gitignored) -> "
              "trained legs skipped (floor legs above still run)")

    # ---- LEG D: trained ensemble at DEMO scale (amplitude saturation) --------
    print("[leg D] trained ensemble — DEMO scale (the demo is floor-carried)")
    if HAS_TRAINED:
        _seed()
        det2 = AnomalyDetector(weights_dir=WEIGHTS, n_healthy=5)
        for w in thermal_windows(15, base_noise, seed0=0)[:5]:
            det2.score(w)
        rows: dict[str, tuple[float, float]] = {}
        for name, ws in [("winter", thermal_windows(15, base_noise)),
                         ("summer", thermal_windows(205, base_noise)),
                         ("rupture", damage_windows(base_noise))]:
            raw = float(np.mean([det2._trained_raw(w)[0] for w in ws]))
            push = max(det2.trained_deviation(w) for w in ws)
            rows[name] = (raw, push)
        push_max = max(p[1] for p in rows.values())
        _check("demo-scale trained push ~0 for healthy AND damage "
               "(< 0.02 — arc cannot be broken by the trained path)",
               push_max < DEMO_SCALE_PUSH_MAX, f"max={push_max:.4f}")
        for name, (raw, push) in rows.items():
            print(f"    {name:8s} raw {raw:.4f}  push {push:.4f}")
    else:
        print("    trained weights absent -> skipped")

    print("\nRESULT", "FAIL" if _FAILS else "PASS", len(_FAILS), "failures")
    return 1 if _FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
