"""
VITISH 2026 · PS#99 SHM — bridge registry (item 14: multi-bridge onboarding).

The hero bridge (z24) and the 49 regulator bridges live in
:mod:`app.regulator_bridges`.  This module adds the ONBOARDING PATH: one or more
EXTRA synthetic live bridges can be added by environment variable alone — no
code change — proving that a new bridge into the network is a CONFIG + registry
exercise, not a fork.

    VITISH_EXTRA_BRIDGES=<id>:<name>:<city>:<state>[:<lat>:<lon>][ , ...]

Example::

    VITISH_EXTRA_BRIDGES=testbridge:Demo Span:Chandigarh:PB:30.73:76.78

Each extra is streamed by the simulator, fused into a per-bridge BHI by fusion,
persisted under its own bridge id, and served by the API (rest inventory + live
state/history under that id) — the SAME fusion + persistence pipeline the hero
uses.  (The WS twin fan-out subscribes to the hero only; extras reach the twin
via REST.)  HONESTY: extra bridges are SIMULATED telemetry (synthetic
channel model / Z24-derived replay), never real sensors; their coordinates are
schematic unless supplied.  Onboarding a REAL bridge is a days-scale engineering
task (sensor + edge-node install, baseline/calibration data, channel-model fit,
registry + config) — NOT a same-day plug-in — which is exactly what
:data:`ONBOARD_LABEL` says and every demo surface must keep saying.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import List, Optional

from app import contract

log = logging.getLogger(__name__)

ENV_VAR = "VITISH_EXTRA_BRIDGES"

# Verbatim honest scoping for "how fast can you onboard a bridge?".  Rehearsed
# answer: config + registry prove the SOFTWARE path is a same-run exercise, but
# a real deployment is days of hardware install + calibration — never "a day".
ONBOARD_LABEL = (
    "Onboarding a new bridge is a days-scale engineering task — sensor + edge-node "
    "install, baseline/calibration data collection, channel-model fit, registry + "
    "config entry — not a same-day plug-in. "
    "Env-driven extra bridges are SIMULATED telemetry (synthetic channel model), "
    "not real sensors; their coordinates are schematic unless supplied."
)

# Each extra carries this honesty tag on every API surface that renders it.
SOURCE_LABEL = "simulated telemetry (synthetic channel model) — not a real sensor; schematic coordinates unless supplied"

# Deterministic schematic coordinate scatter around the hero anchor (Koppigen) so
# an extra without lat/lon still lands on the map instead of (0,0), where the
# twin's fetchBridges deliberately drops zero-coordinate bridges.
_HERO_LAT, _HERO_LON = 47.136, 7.578


def _sanitize_id(bid: str) -> Optional[str]:
    bid = (bid or "").strip().lower()
    if not bid:
        return None
    if bid == contract.BRIDGE_ID:            # never collide with the hero
        return None
    if len(bid) > 24 or not all(c.isalnum() or c == "-" for c in bid):
        return None
    return bid


def _schematic_coords(bid: str) -> tuple:
    seed = int(hashlib.sha1(bid.encode("utf-8")).hexdigest()[:6], 16)
    lat = round(_HERO_LAT + (seed % 97) / 1000.0 - 0.048, 5)
    lon = round(_HERO_LON + (seed // 97 % 89) / 1000.0 - 0.044, 5)
    return lat, lon


def parse_extra_bridges(env_value: str | None = None) -> List[dict]:
    """Parse VITISH_EXTRA_BRIDGES into bridge dicts.  Never raises: malformed
    entries are logged and skipped so a bad env value cannot break boot.

    Format per entry (colon-separated)::

        <id>:<name>:<city>:<state>[:<lat>:<lon>]

    id is lowercased/alnum-dash; name/city/state fall back to the id when empty.
    lat/lon are optional — without them a schematic coordinate near the hero
    anchor is derived deterministically from the id.
    """
    raw = (env_value if env_value is not None else os.getenv(ENV_VAR, "")) or ""
    extras: List[dict] = []
    if not raw.strip():
        return extras
    seen: set = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(":")]
        bid = _sanitize_id(parts[0])
        if bid is None:
            log.warning("bridge registry: skipped malformed extra bridge entry %r", chunk)
            continue
        if bid in seen:
            log.warning("bridge registry: duplicate extra bridge %r — keeping first", bid)
            continue
        seen.add(bid)
        name = parts[1] if len(parts) > 1 and parts[1] else bid
        city = parts[2] if len(parts) > 2 and parts[2] else ""
        state = parts[3] if len(parts) > 3 and parts[3] else ""
        lat, lon = _schematic_coords(bid)
        if len(parts) >= 6:
            try:
                lat = float(parts[4])
                lon = float(parts[5])
            except ValueError:
                pass  # keep the schematic fallback
        extras.append({
            "id": bid,
            "name": name,
            "city": city,
            "state": state,
            "country": "",
            "lat": lat,
            "lon": lon,
            "year_built": None,
            "length_m": None,
            "kind": "synthetic-onboarded",
            "hero": False,
            "live": True,
            "synthetic": True,
            "source_label": SOURCE_LABEL,
            "onboard_label": ONBOARD_LABEL,
        })
    return extras


def extra_bridges() -> List[dict]:
    return parse_extra_bridges()


def extra_bridge_ids() -> List[str]:
    return [b["id"] for b in extra_bridges()]


def is_extra(bridge_id: str) -> bool:
    return bridge_id in extra_bridge_ids()


def live_bridge_ids() -> List[str]:
    """Every bridge with a live (simulated/streaming) data path: hero + extras."""
    return [contract.BRIDGE_ID] + extra_bridge_ids()