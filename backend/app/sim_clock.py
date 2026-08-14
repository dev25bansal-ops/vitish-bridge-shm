"""
D2-8/D2-10 simulated monitoring clock — the backend source of truth for the
twin's "simulated day".

The demo presents the Z24 campaign as a fast time-lapse.  The real Z24
benchmark monitored the bridge from 11 Nov 1997 to 11 Sep 1998 (~305 days);
here the whole monitoring year is folded into a ~6-minute demo, so simulated
days tick at a fixed time-lapse rate.  Every consumer (the stiffness tracker's
seasonal-temperature model today, the twin's "simulated day N/365" label in
D2-8) reads the SAME clock, so temperature and the shown date never desync.

Honesty:
  * This is a SIMULATED calendar, not the bridge's real one.  Any UI label
    must say "simulated day-of-year (time-lapse)", never the bridge's date.
  * The rate is a fixed, documented presentation choice — it does not pretend
    to be sensor time.
"""
from __future__ import annotations

import time

# 11 Nov (day 315) — the real Z24 monitoring campaign start.  Anchoring here
# means the demo opens in late autumn and walks through winter -> summer -> ...
CAMPAIGN_START_DOY = 315.0
# ~2 simulated days per wall-clock second -> one monitoring year in ~3 min of
# demo.  Fixed and documented; the label states the rate so it is auditable.
TIME_LAPSE_DAYS_PER_S = 2.0

_t0 = time.monotonic()


def _reset_t0() -> None:
    """Re-anchor the clock (used by tests to make it deterministic)."""
    global _t0
    _t0 = time.monotonic()


def day_of_year() -> float:
    """Current simulated day-of-year in [1, 365]."""
    elapsed = time.monotonic() - _t0
    return float(((CAMPAIGN_START_DOY - 1.0) + elapsed * TIME_LAPSE_DAYS_PER_S)
                 % 365.0) + 1.0


def label(doy: float | None = None) -> str:
    """Honest human label: 'simulated day N/365 (time-lapse ≈ 2 d/s)'."""
    d = day_of_year() if doy is None else doy
    return (f"simulated day {round(d):d}/365 "
            f"(time-lapse ≈ {TIME_LAPSE_DAYS_PER_S:.0f} simulated d/s)")


if __name__ == "__main__":
    print("simulated monitoring clock (backend source of truth)")
    print("  now  =", label())
    print(f"  rate = {TIME_LAPSE_DAYS_PER_S:.0f} simulated days per wall-clock second")
    # prove the mapping: after R seconds of demo, day = 315 + R*rate (mod 365)
    r = 30.0
    doy = ((CAMPAIGN_START_DOY - 1.0) + r * TIME_LAPSE_DAYS_PER_S) % 365.0 + 1.0
    print(f"  after {r:g}s of demo the simulated day = {label(doy)}")
