"""
NEW-02 · real site temperature for the Koppigen A1 anchor via Open-Meteo.

The Z24 bridge is georeferenced to Koppigen, Switzerland (A1 motorway,
47.136 N / 7.578 E).  Open-Meteo is a free, keyless forecast API, so the twin
can show the REAL air temperature at the bridge site instead of (or alongside)
the simulated seasonal day-of-year model.

Honesty / scope (COMPREHENSIVE-ANALYSIS item 8):
  * The readout is a DISPLAY + provenance feed.  It is NEVER fused into the
    BHI, the anomaly floor, or the thermal residual model — feeding real T
    into those waits for the temperature-normalized retrain, and the
    deterministic demo arc stays untouched.
  * The `source` / `source_label` ALWAYS reflect which model produced the
    value: ``open-meteo`` when the API answered, ``synthetic`` when we fell
    back to the simulated seasonal model.  No surface ever shows "measured"
    when the value is modeled.
  * ``VITISH_SITE_TEMP_DISABLE=1`` forces the offline fallback (no network) —
    the test runner sets it so the gate suite is deterministic and air-gapped.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional

from app import contract
from app import sim_clock
from models.vibration import temperature as thermal

# --- site anchor --------------------------------------------------------------
KOPPIGEN_LAT = 47.136
KOPPIGEN_LON = 7.578
SITE = f"Koppigen A1 ({KOPPIGEN_LAT}, {KOPPIGEN_LON})"

# Open-Meteo forecast endpoint — current conditions, no key, no login.
_API_BASE = "https://api.open-meteo.com/v1/forecast"
_API_URL = (f"{_API_BASE}?latitude={KOPPIGEN_LAT}&longitude={KOPPIGEN_LON}"
            f"&current=temperature_2m")

_FETCH_TIMEOUT_S = 3.0     # bounded so the demo never stalls on a dead network
_CACHE_TTL_S = 900.0       # 15 min — a request every few seconds is rude + pointless

# --- honest source labels ------------------------------------------------------
MEASURED = "open-meteo"
SYNTHETIC = "synthetic"
MEASURED_LABEL = f"measured air temperature — Open-Meteo forecast ({SITE})"
SYNTHETIC_LABEL = ("simulated seasonal temperature (day-of-year model) — "
                   "not a measured sensor")

_NOTE = (
    "air temperature at the real bridge site. Measured via the keyless "
    "Open-Meteo forecast when reachable; falls back to the simulated seasonal "
    "day-of-year model otherwise — the label always reflects the true source. "
    "Display/provenance only: never fused into the BHI, the anomaly floor, or "
    "the thermal residual model until the temperature-normalized retrain exists."
)


def _http_get(url: str, timeout_s: float) -> bytes:
    """GET ``url`` and return the response body (injectable for tests)."""
    with urllib.request.urlopen(url, timeout=timeout_s) as resp:
        return resp.read()


def _parse_current_temp(body: bytes) -> float:
    """Open-Meteo ``current=temperature_2m`` payload -> air temperature (°C)."""
    data = json.loads(body.decode("utf-8"))
    current = data.get("current") or {}
    temp_c = current.get("temperature_2m")
    if not isinstance(temp_c, (int, float)):
        raise ValueError(f"Open-Meteo payload has no current.temperature_2m: {data!r}")
    return float(temp_c)


def _fallback() -> dict:
    """Simulated seasonal value — the honest offline default."""
    doy = sim_clock.day_of_year()
    return {
        "temp_c": round(thermal.seasonal_temp_c(doy), 1),
        "source": SYNTHETIC,
        "source_label": SYNTHETIC_LABEL,
        "cached": False,
        "fetched_at": None,
        "note": _NOTE,
    }


# --- runtime state (single process; benign races — worst case a double probe) ---
_cache: Optional[dict] = None        # {"result": {...}, "at": monotonic}
_network_disabled = os.environ.get("VITISH_SITE_TEMP_DISABLE") == "1"


def set_network_disabled(disabled: bool) -> None:
    """Force the offline fallback (tests / air-gapped runs)."""
    global _network_disabled
    _network_disabled = disabled


def _publish(result: dict) -> dict:
    global _cache
    with_cached = dict(result)
    with_cached["cached"] = True
    _cache = {"result": with_cached, "at": time.monotonic()}
    return with_cached


def probe_site_temp() -> dict:
    """One synchronous probe of the live Open-Meteo API.

    Returns a measured dict on success, the simulated fallback on ANY failure.
    Never raises.  Used by ``get_site_temp`` and by tests with a faked
    ``_http_get``.
    """
    if _network_disabled:
        return _fallback()
    try:
        temp_c = _parse_current_temp(_http_get(_API_URL, _FETCH_TIMEOUT_S))
    except Exception:
        return _fallback()
    return {
        "temp_c": round(temp_c, 1),
        "source": MEASURED,
        "source_label": MEASURED_LABEL,
        "cached": False,
        "fetched_at": contract.now(),
        "note": _NOTE,
    }


def get_site_temp(force_probe: bool = False) -> dict:
    """Honest site-temperature readout for the API / twin.

    Fresh cached value -> returned as-is.  Cold/stale cache -> one synchronous
    probe (bounded by ``_FETCH_TIMEOUT_S``), published under a 15-min TTL.
    Never raises, never claims "measured" when the value is modeled.
    """
    global _cache
    now = time.monotonic()
    if not force_probe and _cache and now - _cache["at"] < _CACHE_TTL_S:
        return dict(_cache["result"])
    return _publish(probe_site_temp())


def reset_site_temp_cache() -> None:
    """Drop the cache so the next read re-probes (test hook)."""
    global _cache
    _cache = None


if __name__ == "__main__":
    st = get_site_temp()
    print(f"[site_temperature] {st['temp_c']}°C  source={st['source']}")
    print(f"  label: {st['source_label']}")
    print(f"  cached: {st['cached']}  fetched_at: {st['fetched_at']}")