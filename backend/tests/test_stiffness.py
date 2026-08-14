"""
Stiffness-overlay regression gate — the Z24 box-girder physics must behave.

The bridge identity is the Z24 14+30+14 m continuous box girder (D1-2
decision).  This gate pins the *physics overlay* that explains the vibration
signal (measured f1 -> EI drift / model-inferred damage / FEM mode shapes).
It must NEVER change the demo arc: the overlay is read-only explainability.

Run:  python backend/tests/test_stiffness.py
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from app import events  # noqa: E402
from app.config import settings  # noqa: E402
from app.stiffness import StiffnessTracker  # noqa: E402
from models.vibration import stiffness as physics  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


def _feed(tracker, bus, f1: float, n_win: int, seed: int = 0) -> None:
    fs, n = 100, 1024
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    for node in settings.nodes:
        for _ in range(n_win):
            x = (0.02 * np.sin(2 * np.pi * f1 * t)
                 + 0.006 * np.sin(2 * np.pi * 4 * f1 * t)
                 + 0.01 * rng.standard_normal(n))
            bus.publish("bridge/z24/accel", {
                "bridge": "z24", "node": node, "ts": time.time(),
                "samples": [float(v) for v in x], "fs": fs,
            })


def _feed_node(tracker, bus, node: int, f1: float, n_win: int,
               seed: int = 0) -> None:
    """Feed accel windows for ONE node (used to isolate the mid-span rule)."""
    fs, n = 100, 1024
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    for _ in range(n_win):
        x = (0.02 * np.sin(2 * np.pi * f1 * t)
             + 0.006 * np.sin(2 * np.pi * 4 * f1 * t)
             + 0.01 * rng.standard_normal(n))
        bus.publish("bridge/z24/accel", {
            "bridge": "z24", "node": node, "ts": time.time(),
            "samples": [float(v) for v in x], "fs": fs,
        })


def test_physics_model() -> None:
    print("[stiffness] Euler-Bernoulli FEM physics")
    # calibrated healthy fundamental
    f1 = physics.fem_modes(n_modes=1)[0][0]
    check("healthy f1 calibrated to 3.80 Hz", abs(f1 - 3.80) < 0.01, f"got {f1}")
    # damage monotone + matches Z24 evidence (10% stiffness -> ~3% f1)
    f1d = physics.f1_of_damage(0.10)
    shift = (f1d / 3.80 - 1.0) * 100
    check("mid-span EI -10% -> f1 shifts ~-3%",
          2.0 <= abs(shift) <= 4.0, f"shift {shift:.2f}%")
    check("more damage -> lower f1", physics.f1_of_damage(0.30) < f1d)
    # reference simple-span proxy
    ei = physics.ei_ref_from_f1(3.80)
    check("reference proxy positive ~6e10", 4e10 < ei < 8e10, f"got {ei:.2e}")
    # damage inversion round-trips
    d = physics.damage_from_f1(physics.f1_of_damage(0.25))
    check("damage_from_f1 round-trips", abs(d - 0.25) < 0.02, f"got {d:.3f}")


def test_tracker() -> None:
    print("[stiffness] live tracker self-baselines + follows f1")
    bus = events.get_bus()
    tracker = StiffnessTracker(settings, bus)
    tracker.start()
    try:
        _feed(tracker, bus, 3.80, 40)
        s = tracker.snapshot()
        check("baseline locked after healthy feed", s["baseline_locked"])
        check("baseline f1 ~3.8", 3.7 <= s["f1_ref"] <= 3.95, str(s["f1_ref"]))
        check("healthy: no drift", s["ei_drift_pct"] < 2.0, str(s["ei_drift_pct"]))
        check("healthy: damage ~0", s["damage_pct"] < 3.0, str(s["damage_pct"]))

        _feed(tracker, bus, 3.52, 25)
        s = tracker.snapshot()
        check("rupture: f1 drops", s["f1_meas"] < s["f1_ref"] - 0.15, str(s))
        check("rupture: EI drift > 8%", s["ei_drift_pct"] > 8.0, str(s["ei_drift_pct"]))
        check("rupture: inferred damage 20-40%",
              20.0 <= s["damage_pct"] <= 40.0, str(s["damage_pct"]))
        check("rupture: first mode tracks f1",
              abs(s["freqs"][0] - s["f1_meas"]) < 0.01, str(s["freqs"]))
        check("mode shapes cover the deck",
              len(s["shapes"]) >= 2 and len(s["x"]) == len(s["shapes"][0]))

        _feed(tracker, bus, 3.80, 25)
        s = tracker.snapshot()
        check("recovery: damage returns to ~0", s["damage_pct"] < 3.0,
              str(s["damage_pct"]))
    finally:
        tracker.stop()


def test_live_honesty() -> None:
    print("[stiffness] live-replay honesty (mid-span rule + contamination guard)")
    bus = events.get_bus()

    # (1) mid-span-only: off-midspan channels (real Z24 ~5.1 Hz higher mode)
    # must never feed the f1 estimate or the baseline.
    t = StiffnessTracker(settings, bus)
    t.start()
    try:
        _feed_node(t, bus, 6, 5.1, 40, seed=11)
        s = t.snapshot()
        check("off-midspan channel alone does not lock baseline",
              not s["baseline_locked"], str(s["f1_meas"]))
        _feed_node(t, bus, 7, 3.8, 40, seed=12)
        s = t.snapshot()
        check("mid-span channel locks baseline at ~3.8",
              s["baseline_locked"] and 3.7 <= s["f1_ref"] <= 3.95,
              str(s["f1_ref"]))
        check("mid-span-only f1 ~3.8 (no 5.1 Hz contamination)",
              abs(s["f1_meas"] - 3.8) < 0.15, str(s["f1_meas"]))
    finally:
        t.stop()

    # (2) forced-tonal guard: a measured f1 RISING above baseline is a forced
    # response, never a stiffness gain — EI drift clamps to 0, no damage claim.
    t = StiffnessTracker(settings, bus)
    t.start()
    try:
        _feed(t, bus, 3.80, 40, seed=21)
        _feed(t, bus, 4.00, 25, seed=22)
        s = t.snapshot()
        check("rising f1 -> EI drift clamped to >= 0 (no 'stiffening')",
              s["ei_drift_pct"] == 0.0, str(s["ei_drift_pct"]))
        check("rising f1 -> no model-inferred damage",
              s["damage_pct"] == 0.0, str(s["damage_pct"]))
        check("rising f1 still reported honestly",
              s["f1_meas"] > s["f1_ref"], str(s))
    finally:
        t.stop()

    # (3) self-calibration: a bridge whose healthy fundamental sits at 3.9 Hz
    # (real Z24) must infer damage from RELATIVE drift, not absolute f1.
    t = StiffnessTracker(settings, bus)
    t.start()
    try:
        _feed(t, bus, 3.90, 40, seed=31)
        s = t.snapshot()
        check("3.9 Hz healthy baseline reads 0 drift",
              s["ei_drift_pct"] < 1.0, str(s["ei_drift_pct"]))
        _feed(t, bus, 3.72, 25, seed=32)
        s = t.snapshot()
        check("relative drop -> EI drift > 5%",
              s["ei_drift_pct"] > 5.0, str(s["ei_drift_pct"]))
        check("relative drop -> inferred damage in 10-30%",
              10.0 <= s["damage_pct"] <= 30.0, str(s["damage_pct"]))
    finally:
        t.stop()


def main() -> int:
    try:
        test_physics_model()
        test_tracker()
        test_live_honesty()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("stiffness tests")
        import traceback
        print(f"  [ERROR] stiffness tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== stiffness gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
