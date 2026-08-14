"""
D2-10 gate — temperature normalization of the first-mode frequency.

The Z24 benchmark's first vertical frequency wanders ~14% peak-to-peak over a
year with air temperature.  This gate pins the simulated seasonal temperature,
the thermal f1 expectation, and — the honest quantity a regulator should look
at — the temperature-compensated residual that is ~0 when healthy at any
temperature and only moves when f1 really leaves its thermal band.

Run:  python backend/tests/test_temperature.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from app import sim_clock  # noqa: E402
from models.vibration import stiffness as physics  # noqa: E402
from models.vibration import temperature as temp  # noqa: E402

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


def test_seasonal_temperature() -> None:
    print("[temperature] simulated seasonal temperature")
    summer = temp.seasonal_temp_c(205)   # 24 Jul — northern-hemisphere peak
    winter = temp.seasonal_temp_c(205 - 182)
    check("summer peak ~27 C", 24.0 <= summer <= 29.0, f"{summer:.1f}")
    check("winter trough ~3 C", 1.0 <= winter <= 6.0, f"{winter:.1f}")
    check("annual mean ~15 C", 14.0 <= temp.SEASONAL_MEAN_C <= 16.0)
    # peak-to-peak seasonal f1 shift reproduces the Z24 ~14% evidence
    p2p = 100.0 * (temp.expected_f1(3.80, winter) / temp.expected_f1(3.80, summer) - 1.0)
    check("full-year f1 wander ~14% (Z24 anchor)",
          11.0 <= p2p <= 17.0, f"{p2p:.1f}%")


def test_thermal_model() -> None:
    print("[temperature] thermal f1 model + residual")
    # at the reference temperature the expectation is the reference f1
    check("T_REF -> expected = f1_ref", abs(temp.expected_f1(3.80, 20.0) - 3.80) < 1e-9)
    check("summer lowers expected f1",
          temp.expected_f1(3.80, 27.0) < 3.80 < temp.expected_f1(3.80, 3.0))
    # healthy bridge at ANY temperature: residual ≈ 0
    for doy in (15, 105, 205, 300):
        t = temp.seasonal_temp_c(doy)
        healthy = temp.residual_drift_pct(temp.expected_f1(3.80, t), 3.80, t)
        check(f"healthy day {doy}: residual ~0", abs(healthy) < 0.01,
              f"{healthy:+.3f}")
    # a REAL ~6% f1 drop must show through even mid-winter (raw f1 looks normal)
    winter = temp.seasonal_temp_c(15)      # ~3 C
    expct = temp.expected_f1(3.80, winter)
    lost = temp.residual_drift_pct(expct * 0.94, 3.80, winter)
    check("real 6% loss shows through residual mid-winter",
          -7.0 <= lost <= -5.0, f"{lost:+.2f}%")
    # a forced rise above expectation is positive (never presented as loss)
    summer = temp.seasonal_temp_c(205)     # ~27 C
    forced = temp.residual_drift_pct(4.00, 3.80, summer)
    check("forced tonal reads POSITIVE residual", forced > 2.0, f"{forced:+.2f}%")


def test_normalize_to_ref() -> None:
    print("[temperature] T_REF normalization of a season-shifted baseline")
    # a tracker baseline measured mid-winter already sits above the 20 C value
    winter_doy, summer_doy = 15, 205
    t_w = temp.seasonal_temp_c(winter_doy)
    t_s = temp.seasonal_temp_c(summer_doy)
    baseline_winter = 3.89  # measured healthy f1 at the winter season
    ref_20c = temp.normalize_to_ref(baseline_winter, t_w)
    check("winter baseline normalizes BELOW itself (cold raises f1)",
          ref_20c < baseline_winter, f"{ref_20c:.3f}")
    # the normalized ref, used as f1_ref, makes the SAME bridge read ~0 residual
    r_w = temp.residual_drift_pct(baseline_winter, ref_20c, t_w)
    check("normalized ref -> residual ~0 at the measured season",
          abs(r_w) < 0.01, f"{r_w:+.3f}")
    # ...but the RAW baseline as f1_ref double-counts the season (false "loss")
    raw = temp.residual_drift_pct(baseline_winter, baseline_winter, t_w)
    check("raw baseline as f1_ref gives a false negative residual",
          raw < -5.0, f"{raw:+.2f}%")
    # a healthy bridge that thermally tracks stays ~0 in summer too
    r_s = temp.residual_drift_pct(
        temp.expected_f1(ref_20c, t_s), ref_20c, t_s)
    check("healthy summer with normalized ref ~0",
          abs(r_s) < 0.01, f"{r_s:+.3f}")


def test_payload_and_wiring() -> None:
    print("[temperature] snapshot payload + sim clock wiring")
    fields = temp.temp_fields(3.80, 3.80, 205)
    for key in ("temp_c", "temp_source", "f1_expected_thermal",
                "thermal_shift_pct", "residual_drift_pct", "residual_band_pct",
                "residual_interpretation", "residual_note", "thermal_model"):
        check(f"temp_fields has '{key}'", key in fields, str(fields.keys()))
    check("temperature labeled simulated, not measured",
          "simulated seasonal temperature" in fields["temp_source"]
          and "not a measured sensor" in fields["temp_source"])
    check("residual sign interpretation documented",
          "stiffness loss" in fields["residual_note"])
    check("residual band ~ Z24 ±7% wander",
          abs(fields["residual_band_pct"] - 7.0) < 0.1,
          str(fields["residual_band_pct"]))
    check("thermal model anchored to Z24 ~14%",
          "14%" in fields["thermal_model"])

    # physics.snapshot: day_of_year drives the overlay; omitted -> no thermal keys
    with_thermal = physics.snapshot(3.80, 3.80, day_of_year=205)
    check("snapshot(day_of_year) carries temp_c",
          "temp_c" in with_thermal and "residual_drift_pct" in with_thermal)
    check("summer snapshot thermal shift is NEGATIVE (f1 lower in heat)",
          with_thermal["thermal_shift_pct"] < 0, str(with_thermal["thermal_shift_pct"]))
    plain = physics.snapshot(3.80, 3.80)
    check("snapshot() without day_of_year has no thermal keys",
          "temp_c" not in plain and "sim_day" not in plain)

    # sim clock is deterministic, in-range, honestly labelled
    sim_clock._reset_t0()
    doy = sim_clock.day_of_year()
    check("sim day in [1,365]", 1.0 <= doy <= 365.0, f"{doy:.1f}")
    lab = sim_clock.label(doy)
    check("clock label says 'simulated day' + time-lapse",
          "simulated day" in lab and "time-lapse" in lab, lab)
    check("clock anchored at campaign start (11 Nov ~day 315)",
          314.0 <= doy <= 316.0, f"{doy:.1f}")
    # mapping formula: 30 s of demo -> ~60 simulated days later (mod 365)
    later = ((sim_clock.CAMPAIGN_START_DOY - 1.0)
             + 30.0 * sim_clock.TIME_LAPSE_DAYS_PER_S) % 365.0 + 1.0
    expected = (doy - 1.0 + 60.0) % 365.0 + 1.0
    check("time-lapse mapping advances ~2 d/s",
          abs(later - expected) < 0.01, f"{later:.1f} vs {expected:.1f}")


def main() -> int:
    try:
        test_seasonal_temperature()
        test_thermal_model()
        test_normalize_to_ref()
        test_payload_and_wiring()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("temperature tests")
        import traceback
        print(f"  [ERROR] temperature tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== temperature gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
