"""
VITISH 2026 · PS#99 SHM — item 14: multi-bridge registry test.

Run from backend/:  python tests/test_multi_bridge.py

Proves the env-driven bridge-registry onboarding path with no broker and no
Postgres: registry parsing + honesty labels, default 50-bridge inventory
parity, the enriched 50+N inventory when an extra bridge is configured, the
fusion routing that streams a per-extra BHI through the SAME pipeline as the
hero, and the hard rule that the extra path NEVER touches the model baseline
(get_anomaly / last_evidence) that belongs to the hero path.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import numpy as np

from app import bridge_registry, contract, db, events  # noqa: E402
from app.config import settings  # noqa: E402
from app.events import EventBus  # noqa: E402
from app.fusion import FusionService  # noqa: E402
from app.mqtt_client import Publisher  # noqa: E402
from app.regulator_bridges import all_bridges, find_bridge, geojson  # noqa: E402
from app.simulator import SyntheticPlayer  # noqa: E402

_ENV = bridge_registry.ENV_VAR

# Start the file in the DEFAULT (no extras) state so parity is deterministic
# regardless of how the runner launched this process.
_SAVED_ENV = os.environ.get(_ENV)
os.environ.pop(_ENV, None)

PASS = 0
FAIL = 0


def check(name, cond, info=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok: {name}")
    else:
        FAIL += 1
        print(f"FAIL: {name}  {info}")


class FakePublisher(Publisher):
    """In-memory publisher: captures bhi envelopes, never connects to MQTT."""

    def __init__(self):
        self.connected = threading.Event()
        self.connected.set()
        self.accel = []
        self.bhi = []

    def publish(self, topic, payload, qos=0):  # pragma: no cover - never used
        if topic.endswith("/bhi"):
            self.bhi.append(payload)
        return True


def set_env(value):
    os.environ.pop(_ENV, None)
    if value is not None:
        os.environ[_ENV] = value


def feed(bus, bridge_id, samples, node=7):
    bus.publish(f"bridge/{bridge_id}/accel", {
        "bridge": bridge_id, "node": node, "ts": time.time(),
        "samples": list(samples), "fs": 100,
    })


def main():
    print("[1] default inventory parity (no extra bridges)")
    bridges = all_bridges()
    check("default inventory is exactly 50", len(bridges) == 50, str(len(bridges)))
    check("hero is first + live", bridges[0]["id"] == "z24" and bridges[0]["live"] is True)
    check("no synthetic tag in default inventory",
          not any(b.get("synthetic") for b in bridges))
    geo = geojson()
    check("default geojson has 50 features", len(geo["features"]) == 50,
          str(len(geo["features"])))
    check("no synthetic tag in default geojson",
          not any(f["properties"].get("synthetic") for f in geo["features"]))
    print()

    print("[2] registry parsing (env literal, no process env needed)")
    parsed = bridge_registry.parse_extra_bridges(
        "  goodbridge:Demo Span:City X:PB:30.73:76.78 , "
        "BAD_ID!:x:y:z, dup:One:A:B, DUP:Two:C:D, z24:evil:bad:nope, "
        ",nocoord:No Coord:A:B")
    ids = [b["id"] for b in parsed]
    check("2 valid extras parsed (malformed/dups/hero-collision skipped)",
          ids == ["goodbridge", "dup", "nocoord"], str(ids))
    g = parsed[0]
    check("explicit lat/lon honoured", g["lat"] == 30.73 and g["lon"] == 76.78,
          str((g["lat"], g["lon"])))
    n = parsed[2]
    check("missing coords -> schematic (never 0,0)",
          n["lat"] != 0 and n["lon"] != 0 and 46.0 <= n["lat"] <= 48.0,
          str((n["lat"], n["lon"])))
    check("extras are hero=False, live=True, synthetic=True",
          all(not b["hero"] and b["live"] and b["synthetic"] for b in parsed))
    check("every extra carries source_label",
          all("simulated telemetry" in b["source_label"] for b in parsed))
    check("ONBOARD_LABEL scopes honestly (days-scale, not same-day)",
          "days-scale" in bridge_registry.ONBOARD_LABEL
          and "not a same-day plug-in" in bridge_registry.ONBOARD_LABEL
          and "SIMULATED telemetry" in bridge_registry.ONBOARD_LABEL)
    check("SOURCE_LABEL names the synthetic channel",
          "synthetic channel model" in bridge_registry.SOURCE_LABEL)
    r = bridge_registry.parse_extra_bridges("")
    check("empty env -> no extras", r == [])
    print()

    print("[3] env-on inventory (50 + 2 extra synthetic bridges)")
    set_env("testbridge:Test Span:Testing:TS, altbridge:Alt Deck:Alt:AL")
    ids = bridge_registry.extra_bridge_ids()
    check("extra_bridge_ids() == 2", ids == ["testbridge", "altbridge"], str(ids))
    bridges = all_bridges()
    check("inventory is 52 with 2 extras", len(bridges) == 52, str(len(bridges)))
    tail = bridges[-2:]
    check("extras appended last, enriched",
          [b["id"] for b in tail] == ["testbridge", "altbridge"]
          and all(b["synthetic"] and b["live"] and b["bhi"] == 87.0
                  and b["state"] == "GREEN" for b in tail),
          str([(b["id"], b["bhi"], b["state"]) for b in tail]))
    fb = find_bridge("testbridge")
    check("find_bridge resolves an extra",
          fb is not None and fb["id"] == "testbridge" and fb["synthetic"] is True)
    geo = geojson()
    check("geojson has 52 features + synthetic property on extras",
          len(geo["features"]) == 52
          and geo["features"][-1]["properties"]["synthetic"] is True,
          str(len(geo["features"])))
    print()

    print("[4] fusion routes hero + extra through the same pipeline")
    import app.fusion as fusion_mod
    orig_anomaly = fusion_mod.get_anomaly
    orig_evidence = fusion_mod.last_evidence
    calls = {"anomaly": 0, "evidence": 0}

    def _spy_anomaly(window, fs=100):
        calls["anomaly"] += 1
        return orig_anomaly(window, fs=fs)

    def _spy_evidence():
        calls["evidence"] += 1
        return orig_evidence()

    fusion_mod.get_anomaly = _spy_anomaly
    fusion_mod.last_evidence = _spy_evidence

    bus = EventBus()          # fresh bus: no cross-test residue
    pub = FakePublisher()
    fus = FusionService(settings, bus, db.MemoryStore(cache_path=None), pub)
    fus.start()
    try:
        # feed ONLY extra accel, plenty of bursts (well past window_n): the
        # extra path must never call the model baseline.
        extra = SyntheticPlayer("healthy", [7], seed=3)
        for _ in range(40):
            feed(bus, "testbridge", extra.current_window(7))
            extra.tick()
        check("extra accel never calls get_anomaly", calls["anomaly"] == 0,
              str(calls["anomaly"]))
        check("extra accel never calls last_evidence", calls["evidence"] == 0,
              str(calls["evidence"]))
        extra_bhi = [p for p in pub.bhi if p["bridge"] == "testbridge"]
        check("extra BHI envelope flows on the same pipeline",
              len(extra_bhi) >= 1, f"{len(extra_bhi)} envelopes")
        if extra_bhi:
            p = extra_bhi[-1]
            check("extra BHI carries contract keys",
                  all(k in p for k in
                      ("bridge", "ts", "bhi", "u", "cv", "vib", "load", "state")))
            check("extra BHI HEALTHY GREEN (~baseline), not fabricated damage",
                  80.0 <= p["bhi"] <= 95.0 and p["state"] == "GREEN",
                  str((p["bhi"], p["state"])))
            check("extra BHI is honestly tagged simulated-extra",
                  p.get("source") == "simulated-extra")

        # hero still drives the model baseline normally afterwards.
        hero = SyntheticPlayer("healthy", [7], seed=1)
        for _ in range(14):   # 14*100 > 1024 window_n -> get_anomaly fires
            feed(bus, "z24", hero.current_window(7))
            hero.tick()
        check("hero accel DOES call get_anomaly", calls["anomaly"] >= 1,
              str(calls["anomaly"]))
        check("hero accel DOES call last_evidence", calls["evidence"] >= 1,
              str(calls["evidence"]))
        hero_bhi = [p for p in pub.bhi if p["bridge"] == "z24"]
        check("hero BHI envelope flows", len(hero_bhi) >= 1)
        if hero_bhi:
            p = hero_bhi[-1]
            check("hero BHI GREEN and healthy (arc intact)",
                  p["state"] == "GREEN" and 80.0 <= p["bhi"] <= 95.0,
                  str((p["bhi"], p["state"])))

        # a non-registry bridge is ignored by fusion (no BHI invented for it).
        ghost = SyntheticPlayer("healthy", [7], seed=9)
        for _ in range(20):
            feed(bus, "ghost", ghost.current_window(7))
            ghost.tick()
        check("non-registry bridge gets no BHI envelope",
              not any(p["bridge"] == "ghost" for p in pub.bhi))
    finally:
        fus.stop()
        fusion_mod.get_anomaly = orig_anomaly
        fusion_mod.last_evidence = orig_evidence
    print()

    print("[5] /api/config serves the multi_bridge honesty surface")
    try:
        db.reset_store()
        db.get_store(settings, prefer="memory")
        from fastapi.testclient import TestClient
        import app.api as api_mod
        client = TestClient(api_mod.create_app())
        cfg = client.get("/api/config").json()
        mb = cfg.get("multi_bridge", {})
        check("/api/config exposes multi_bridge block", bool(mb))
        check("multi_bridge lists the 2 extras",
              [e["id"] for e in mb.get("extra_bridges", [])] == ["testbridge", "altbridge"],
              str([e["id"] for e in mb.get("extra_bridges", [])]))
        check("multi_bridge carries the honest ONBOARD_LABEL",
              "not a same-day plug-in" in mb.get("onboard_label", ""))
        bridges_resp = client.get("/api/bridges").json()
        check("/api/bridges counts 52 with extras", bridges_resp["count"] == 52,
              str(bridges_resp["count"]))
        check("extra serialized with honesty tags in the bridge list",
              all(e.get("synthetic") and e.get("source_label")
                  and e.get("onboard_label")
                  for e in bridges_resp["bridges"][-2:]))
        hist = client.get("/api/bridge/testbridge/history?metric=bhi").json()
        check("extra bridge history endpoint 200 (live store path)",
              "data" in hist and hist["bridge"] == "testbridge", str(hist)[:80])
    finally:
        db.reset_store()
    print()

    set_env(_SAVED_ENV)   # restore whatever the runner had on entry

    print(f"== {PASS} PASS / {FAIL} FAIL ==")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())