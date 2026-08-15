"""
VITISH 2026 · PS#99 SHM — regulator bridge network (illustrative data).

The hero bridge ``z24`` streams the real benchmark through the real pipeline;
the other 49 bridges are *illustrative* — real US locations (NBI/OSM-derived)
with simulated health — shown to demonstrate the regulator map view.  This is a
deliberate disclosure beat in the demo script, never presented as live data.

Health is deterministic (seeded per bridge id) so the map is stable across
restarts while still showing a realistic spread of GREEN / AMBER / RED — the
seeded floor is 40.0 and the ceiling 98.0, so the full state range is reachable
(about 26 GREEN / 16 AMBER / 6 RED across the 49 at the current draw, verified
by test).  The 49 healths are computed ONCE and cached: they never change (they
are seeded, not live), so every /api/bridges request reuses the same values
instead of re-hashing and re-drawing 49 times.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import List

import numpy as np

from app import contract

# (name, city, state, lat, lon, year_built, length_m, kind)
_REGULATORS: List[tuple] = [
    ("Golden Gate Bridge", "San Francisco", "CA", 37.8199, -122.4783, 1937, 2737, "suspension"),
    ("Brooklyn Bridge", "New York", "NY", 40.7061, -73.9969, 1883, 1825, "suspension"),
    ("George Washington Bridge", "Fort Lee", "NJ", 40.8517, -73.9527, 1931, 1451, "suspension"),
    ("Verrazzano-Narrows Bridge", "New York", "NY", 40.6066, -74.0447, 1964, 1298, "suspension"),
    ("Mackinac Bridge", "St. Ignace", "MI", 45.8173, -84.7275, 1957, 1158, "suspension"),
    ("San Francisco-Oakland Bay Bridge", "Oakland", "CA", 37.7980, -122.3770, 1936, 704, "suspension"),
    ("Tacoma Narrows Bridge", "Tacoma", "WA", 47.2689, -122.5520, 1950, 1646, "suspension"),
    ("Sunshine Skyway Bridge", "Tampa", "FL", 27.6217, -82.6558, 1987, 402, "cable-stayed"),
    ("Chesapeake Bay Bridge", "Annapolis", "MD", 38.9926, -76.3820, 1952, 6914, "steel-girder"),
    ("Bayonne Bridge", "Bayonne", "NJ", 40.6424, -74.1426, 1931, 504, "steel-arch"),
    ("Lake Pontchartrain Causeway", "New Orleans", "LA", 30.1997, -90.1208, 1956, 38352, "prestressed-concrete"),
    ("Huey P. Long Bridge", "Jefferson", "LA", 29.9396, -90.1693, 1935, 844, "steel-truss"),
    ("Coronado Bridge", "San Diego", "CA", 32.6905, -117.1580, 1969, 2257, "prestressed-concrete"),
    ("Fremont Bridge", "Seattle", "WA", 47.6474, -122.3500, 1917, 150, "vertical-lift"),
    ("Astoria-Megler Bridge", "Astoria", "OR", 46.2095, -123.8514, 1966, 6456, "steel-truss"),
    ("I-35W St. Anthony Falls Bridge", "Minneapolis", "MN", 44.9797, -93.2450, 2008, 381, "post-tensioned-concrete"),
    ("Ambassador Bridge", "Detroit", "MI", 42.3120, -83.0740, 1929, 564, "suspension"),
    ("Blue Water Bridge", "Port Huron", "MI", 42.9990, -82.4230, 1938, 560, "steel-arch"),
    ("Zilwaukee Bridge", "Zilwaukee", "MI", 43.4826, -83.9210, 1988, 2402, "segmental-concrete"),
    ("Bob Kerrey Pedestrian Bridge", "Omaha", "NE", 41.2620, -95.9250, 2008, 947, "cable-stayed"),
    ("Broadway Bridge", "Portland", "OR", 45.5320, -122.6730, 1913, 409, "double-leaf-bascule"),
    ("Sagamore Bridge", "Bourne", "MA", 41.7717, -70.5445, 1935, 421, "steel-truss"),
    ("Tobin Memorial Bridge", "Boston", "MA", 42.3850, -71.0520, 1950, 1122, "steel-girder"),
    ("Zakim Bridge", "Boston", "MA", 42.3680, -71.0740, 2002, 436, "cable-stayed"),
    ("Tappan Zee (Mario Cuomo) Bridge", "Tarrytown", "NY", 41.0712, -73.9250, 2017, 4901, "cable-stayed"),
    ("RFK (Triborough) Bridge", "New York", "NY", 40.7833, -73.9270, 1936, 822, "suspension"),
    ("Throgs Neck Bridge", "New York", "NY", 40.8020, -73.7920, 1961, 549, "suspension"),
    ("Bronx-Whitestone Bridge", "New York", "NY", 40.8010, -73.8280, 1939, 701, "suspension"),
    ("Pulaski Skyway", "Jersey City", "NJ", 40.7306, -74.0920, 1932, 5633, "steel-truss"),
    ("Walt Whitman Bridge", "Philadelphia", "PA", 39.9053, -75.1460, 1957, 610, "suspension"),
    ("Ben Franklin Bridge", "Camden", "NJ", 39.9520, -75.1330, 1926, 533, "suspension"),
    ("Commodore Barry Bridge", "Chester", "PA", 39.8250, -75.3770, 1974, 501, "steel-arch"),
    ("Delaware Memorial Bridge", "New Castle", "DE", 39.6860, -75.5200, 1951, 655, "suspension"),
    ("Chesapeake Bay Bridge-Tunnel", "Virginia Beach", "VA", 37.0333, -76.0667, 1964, 28326, "bridge-tunnel"),
    ("Lake Champlain Bridge", "Crown Point", "NY", 43.8400, -73.4140, 2011, 1310, "steel-arch"),
    ("Sherman Minton Bridge", "Louisville", "KY", 38.2800, -85.8200, 1962, 1372, "steel-truss"),
    ("Clark Memorial Bridge", "Louisville", "KY", 38.2640, -85.7850, 1929, 762, "steel-truss"),
    ("Hernando de Soto Bridge", "Memphis", "TN", 35.1580, -90.0890, 1973, 1369, "steel-arch"),
    ("Harahan Bridge", "Memphis", "TN", 35.1320, -90.0680, 1916, 1580, "steel-truss"),
    ("Eads Bridge", "St. Louis", "MO", 38.6260, -90.1800, 1874, 520, "steel-arch"),
    ("Stan Musial Veterans Memorial Bridge", "St. Louis", "MO", 38.6220, -90.1840, 2014, 606, "cable-stayed"),
    ("Chain of Rocks Bridge", "Madison", "IL", 38.6950, -90.1890, 1929, 1631, "steel-truss"),
    ("Royal Gorge Bridge", "Cañon City", "CO", 38.4610, -105.2450, 1929, 384, "suspension"),
    ("Bixby Creek Bridge", "Big Sur", "CA", 36.3710, -121.9010, 1932, 218, "concrete-arch"),
    ("Rainbow Bridge", "Niagara Falls", "NY", 43.0900, -79.0690, 1941, 289, "steel-arch"),
    ("Peace Bridge", "Buffalo", "NY", 42.9070, -78.9040, 1927, 1140, "steel-truss"),
    ("Woodrow Wilson Bridge", "Alexandria", "VA", 38.7920, -77.0420, 1961, 549, "bascule"),
    ("I-74 Mississippi River Bridge", "Moline", "IL", 41.4830, -90.5310, 2019, 1253, "cable-stayed"),
    ("Fort Pitt Bridge", "Pittsburgh", "PA", 40.4410, -80.0110, 1959, 358, "steel-arch"),
]

HERO = {
    "id": "z24",
    "name": "Z24 Benchmark Bridge (PS#99 hero)",
    "city": "Nottwil",
    "state": "LU",
    "country": "Switzerland",
    "lat": 47.135,
    "lon": 8.165,
    "year_built": 1979,
    "length_m": 58,
    "kind": "post-tensioned-concrete-box-girder",
    "hero": True,
}

_STATE_COLORS = {"GREEN": "#16a34a", "AMBER": "#f59e0b", "RED": "#dc2626"}


def simulated_health(bridge_id: str) -> tuple:
    """Deterministic (bhi, state) for a regulator bridge id.

    Range [40.0, 98.0] (previously [62.0, 98.0]) so the full state spread is
    reachable: a floor of 62 made RED (bhi < 50) impossible, contradicting the
    module docstring's GREEN / AMBER / RED claim (ROADMAP line 47).  ~12.6% of
    draws fall below 50, so the 49-bridge map shows a realistic ~6 RED.
    """
    seed = int(hashlib.sha1(bridge_id.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    bhi = round(40.0 + 58.0 * (rng.random() ** 0.85), 1)
    return bhi, contract.state_for(bhi)


@lru_cache(maxsize=1)
def _all_regulator_healths() -> dict:
    """Per-id (bhi, state) for every regulator, computed once.

    Deterministic and immutable (seeded, not live), so caching is safe.  Without
    this, /api/bridges calls all_bridges() three times per request and each call
    re-hashes + re-draws all 49 (ROADMAP line 47 perf).
    """
    return {f"reg-{idx:02d}": simulated_health(f"reg-{idx:02d}")
            for idx in range(1, len(_REGULATORS) + 1)}


def _regulator_dict(idx: int, row: tuple) -> dict:
    name, city, state, lat, lon, year, length, kind = row
    bid = f"reg-{idx:02d}"
    bhi, hstate = _all_regulator_healths()[bid]
    return {
        "id": bid,
        "name": name,
        "city": city,
        "state": state,
        "country": "USA",
        "lat": lat,
        "lon": lon,
        "year_built": year,
        "length_m": length,
        "kind": kind,
        "bhi": bhi,
        "state": hstate,
        "color": _STATE_COLORS[hstate],
        "hero": False,
        "live": False,
    }


def all_bridges(hero_bhi: float | None = None,
                hero_state: str | None = None) -> List[dict]:
    """Return hero + 49 regulators with health. ``hero_bhi`` overrides live value."""
    hero = dict(HERO)
    if hero_bhi is None:
        hero_bhi, hero_state = 87.0, "GREEN"
    hero["bhi"] = hero_bhi
    hero["state"] = hero_state or contract.state_for(hero_bhi)
    hero["color"] = _STATE_COLORS[hero["state"]]
    hero["live"] = True
    regs = [_regulator_dict(i, row) for i, row in enumerate(_REGULATORS, start=1)]
    return [hero] + regs


def find_bridge(bridge_id: str) -> dict | None:
    for b in all_bridges():
        if b["id"] == bridge_id:
            return b
    return None


def geojson(hero_bhi: float | None = None, hero_state: str | None = None) -> dict:
    features = []
    for b in all_bridges(hero_bhi=hero_bhi, hero_state=hero_state):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]},
            "properties": {
                "id": b["id"],
                "name": b["name"],
                "location": f"{b['city']}, {b['state']}",
                "bhi": b["bhi"],
                "state": b["state"],
                "color": b["color"],
                "hero": b["hero"],
                "live": b.get("live", False),
            },
        })
    return {"type": "FeatureCollection", "features": features}
