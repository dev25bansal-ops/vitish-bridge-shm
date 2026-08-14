"""
D2-10 · temperature normalization of the first-mode frequency.

The Z24 benchmark's first vertical frequency shifts ~14% peak-to-peak over the
year with air temperature — thermal wandering is the #1 false-damage source in
vibration-based SHM (it can look exactly like stiffness loss).  This module
provides the two pieces the honest overlay needs:

  1. ``seasonal_temp_c`` — a synthesized seasonal air-temperature signal
     (LABELED "simulated"), driven by a day-of-year so the twin's "simulated
     day" clock and the thermal model stay in sync.
  2. ``expected_f1`` / ``residual_drift_pct`` — the thermal f1 response
     anchored to the Z24 published seasonal shift (~14% / yr) and the
     temperature-compensated residual that isolates REAL stiffness loss from
     thermal drift.

Honesty:
  * The temperature is SIMULATED and the thermal coefficient is a MODEL
    anchored to Z24's documented seasonal shift — never presented as a measured
    sensor time series.
  * ``residual_drift_pct`` is the quantity a regulator should look at: it is
    ~0 when healthy (even mid-summer) and only moves when the modal frequency
    really leaves its thermal band.
"""
from __future__ import annotations

import math

# --- calibration ---------------------------------------------------------------
# Z24 evidence: first vertical frequency drifts ~14% peak-to-peak over the year
# with air temperature (published seasonal effect).  Anchored so that a full
# seasonal amplitude (amp_c below) reproduces that ~14% swing.
SEASONAL_SHIFT_PCT = 14.0     # published Z24 peak-to-peak seasonal f1 shift (%)
T_REF_C = 20.0                # reference air temperature for f1_ref
SEASONAL_MEAN_C = 15.0        # synthetic annual mean air temperature (°C)
SEASONAL_AMP_C = 12.0         # synthetic seasonal amplitude (°C) -> ~3..27 °C

# per-°C coefficient: alpha such that 2*amp_c * alpha = seasonal_shift / 100
ALPHA_PER_C = (SEASONAL_SHIFT_PCT / 100.0) / (2.0 * SEASONAL_AMP_C)


def seasonal_temp_c(day_of_year: float, mean_c: float = SEASONAL_MEAN_C,
                    amp_c: float = SEASONAL_AMP_C,
                    summer_peak_day: int = 205) -> float:
    """Synthetic air temperature for a day-of-year (1..365).

    Simple seasonal sinusoid peaking ~24 July (day 205, northern hemisphere).
    LABELED simulated: the twin's overlay must say "simulated temperature", not
    "measured".
    """
    phase = 2.0 * math.pi * (day_of_year - summer_peak_day) / 365.0
    return float(mean_c + amp_c * math.cos(phase))


def thermal_shift_pct(f1_ref: float, temp_c: float) -> float:
    """% shift of the thermal expectation vs the reference f1 at T_REF_C."""
    if f1_ref <= 0:
        return 0.0
    return round(100.0 * (-ALPHA_PER_C * (temp_c - T_REF_C)), 2)


def expected_f1(f1_ref: float, temp_c: float) -> float:
    """The f1 the bridge should show at temp_c if it is healthy (thermal model)."""
    return f1_ref * (1.0 - ALPHA_PER_C * (temp_c - T_REF_C))


def residual_drift_pct(f1_meas: float, f1_ref: float, temp_c: float) -> float:
    """Temperature-compensated drift: f1 vs its THERMAL expectation, as %.

    ~0 when healthy at any temperature; negative only when the modal frequency
    genuinely leaves its thermal band (real stiffness loss).  This is the
    quantity that separates thermal wandering from damage.
    """
    expct = expected_f1(f1_ref, temp_c)
    if expct <= 0:
        return 0.0
    return round(100.0 * (f1_meas / expct - 1.0), 2)


def normalize_to_ref(f1_at_t: float, temp_c: float) -> float:
    """The f1 this bridge would show at the reference temperature (T_REF_C),
    given its f1 measured at ``temp_c``.

    Used by a live tracker to convert its self-baseline (measured at whatever
    season the demo is in) into a T_REF-anchored thermal reference.  Without
    this the residual would double-count the season: a baseline measured in
    winter already sits ~10% above the 20 C value, and comparing it to a
    winter-thermal expectation would show a false ~-10% "loss" on a healthy
    bridge.
    """
    if f1_at_t <= 0:
        return f1_at_t
    return f1_at_t / (1.0 - ALPHA_PER_C * (temp_c - T_REF_C))


def residual_band_pct() -> float:
    """± thermal band (%) around the expectation inside which a healthy bridge
    stays.  Anchored to the Z24 published seasonal f1 wander (~14% peak-to-peak
    → ±7%): any residual beyond this band is a real departure, not season."""
    return round(SEASONAL_SHIFT_PCT / 2.0, 1)


def temp_fields(f1_meas: float, f1_ref: float, day_of_year: float) -> dict:
    """One self-describing thermal overlay payload for the stiffness snapshot.

    ``f1_ref`` is the healthy reference at T_REF_C (20 C) — a tracker should
    pass ``normalize_to_ref(baseline, temp_at_baseline)``, not the raw
    season-shifted baseline.
    """
    temp_c = round(seasonal_temp_c(day_of_year), 1)
    expct = expected_f1(f1_ref, temp_c)
    resid = residual_drift_pct(f1_meas, f1_ref, temp_c)
    band = residual_band_pct()
    if abs(resid) < band:
        interp = "within thermal band — consistent with healthy"
    elif resid < 0:
        interp = "below thermal band — f1 below expectation (consistent with stiffness loss)"
    else:
        interp = "above thermal band — f1 above expectation (forced response, never stiffness gain)"
    return {
        "temp_c": temp_c,
        "temp_source": "simulated seasonal temperature (day-of-year model) — not a measured sensor",
        "f1_expected_thermal": round(expct, 3),
        "thermal_shift_pct": thermal_shift_pct(f1_ref, temp_c),
        "residual_drift_pct": resid,
        "residual_band_pct": band,
        "residual_interpretation": interp,
        "residual_note": ("residual_drift_pct < 0 = f1 below its thermal "
                          "expectation (consistent with stiffness loss); ≈0 = "
                          "healthy at any temperature; >0 = above expectation "
                          "(forced response — never stiffness gain); "
                          f"±{band:.0f}% band = the Z24 seasonal wander, inside "
                          "which healthy stays"),
        "thermal_model": f"f1(T) = f1_ref * (1 - {ALPHA_PER_C:.5f}·(T - {T_REF_C}C)), "
                         f"anchored to Z24 ~{SEASONAL_SHIFT_PCT:.0f}% seasonal shift",
    }


if __name__ == "__main__":
    F1_REF = 3.80  # healthy reference f1 (Hz)
    for doy in (15, 105, 205, 300):
        t = round(seasonal_temp_c(doy), 1)
        # healthy bridge: measured f1 tracks its THERMAL expectation at T
        healthy = temp_fields(expected_f1(F1_REF, t), F1_REF, doy)
        print(f"day {doy:3d}: T={t:5.1f}C  expected={healthy['f1_expected_thermal']:.3f} Hz "
              f"thermal={healthy['thermal_shift_pct']:+.2f}%  "
              f"residual(healthy)={healthy['residual_drift_pct']:+.2f}%")
    # a real ~6% f1 drop (stiffness loss) mid-summer must show through the residual
    # even though the raw f1 sits inside the healthy winter band:
    winter = temp_fields(expected_f1(F1_REF, seasonal_temp_c(15)) * 0.94, F1_REF, 15)
    print("winter f1 minus 6% real loss: residual =", winter["residual_drift_pct"], "%")
