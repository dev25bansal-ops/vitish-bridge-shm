"""
VITISH 2026 · PS#99 SHM — live public-MQTT feed unit test (no network required).

Run from backend/:  python tests/smoke_live_feed_unit.py

Deterministically proves the adapter + persistence path that the live feed
depends on, WITHOUT the intermittent public broker:
  1. LiveFeed._adapt maps each public namespace to the right bus topic + shape
     (MSU RMS -> contract accel rows on bridge/live-demo/accel; Vel/Disp, Temp,
     Humidity, shm DAQ, Tilt, CNN -> bridge/live-demo/telemetry; junk -> []).
  2. The recorder (pattern="bridge/live-demo/#") persists live-demo accel rows
     into the store and does NOT see bridge/z24/# events (hero arc untouched).
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import contract, db, events
from app.config import Settings
from app.live_feed import LiveFeed, _num, _AXIS_NODE

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


class _FakeBus:
    """Captures publishes so we can assert on them without a real event bus."""

    def __init__(self):
        self.published = []

    def publish(self, topic, payload, source=None):
        self.published.append((topic, payload, source))


def _make_feed():
    return LiveFeed(_FakeBus())


def test_adapt_namespaces():
    print("== namespace adapters ==")
    feed = _make_feed()

    # MSU RMS X -> accel node 1 with the RMS value (persisted row)
    evs = feed._adapt("MSU/Accelerometer/RMS/X/LOC_MSU-0000002", "0.0045821")
    check("MSU RMS X -> 1 accel event", len(evs) == 1)
    if evs:
        topic, payload = evs[0]
        check("MSU RMS X topic", topic == "bridge/live-demo/accel")
        check("MSU RMS X node=1", payload.get("node") == _AXIS_NODE["x"] == 1)
        check("MSU RMS X rms parsed", abs(payload.get("rms", -1) - 0.0045821) < 1e-6)
        check("MSU RMS X flagged clean", payload.get("flag") == 0)
        check("MSU RMS X honest tags",
              payload.get("bridge") == "live-demo"
              and payload.get("source") == "public-mosquitto")

    # MSU RMS Z -> node 3
    evs = feed._adapt("MSU/Accelerometer/RMS/Z/LOC_MSU-0000002", {"value": 1.25})
    check("MSU RMS Z dict payload -> node=3", evs and evs[0][1]["node"] == 3)
    check("MSU RMS Z rms from dict value", evs and evs[0][1]["rms"] == 1.25)

    # Vel / Disp scalars -> telemetry (not accel rows)
    evs = feed._adapt("MSU/Accelerometer/Vel/X/LOC_MSU-0000002", 0.31)
    check("MSU Vel -> telemetry", len(evs) == 1 and evs[0][0].endswith("/telemetry"))
    evs = feed._adapt("MSU/Accelerometer/Disp/Y/LOC_MSU-0000002", -0.002)
    check("MSU Disp -> telemetry", len(evs) == 1 and evs[0][0].endswith("/telemetry"))

    # Temperature / Humidity -> telemetry
    evs = feed._adapt("MSU/Temperature/Ambient/LOC_MSU-0000002", "21.4")
    check("MSU Temperature -> telemetry", len(evs) == 1 and evs[0][1]["metric"] == "temperature")
    evs = feed._adapt("MSU/Humidity/Ambient/LOC_MSU-0000002", 48.2)
    check("MSU Humidity -> telemetry", len(evs) == 1 and evs[0][1]["metric"] == "humidity")

    # shm DAQ JSON -> telemetry with the raw dict preserved
    daq = {"temperature": 24.1, "pressure": 1013.2, "flag": 0}
    evs = feed._adapt("shm/usb3134a/data", daq)
    check("shm DAQ -> telemetry", len(evs) == 1 and evs[0][1]["metric"] == "daq")
    check("shm DAQ raw dict preserved", evs and evs[0][1]["data"] == daq)

    # TiltSensor / CNN -> telemetry
    evs = feed._adapt("TiltSensor/1/Angle", 0.7)
    check("TiltSensor -> telemetry", len(evs) == 1 and evs[0][1]["metric"] == "tilt")
    evs = feed._adapt("CNN/Forno1/Tags/GET", {"rpm": 120})
    check("CNN -> telemetry", len(evs) == 1 and evs[0][1]["metric"] == "machinery-vib")

    # unknown / non-numeric -> dropped
    evs = feed._adapt("MSU/Accelerometer/RMS/X/LOC_MSU-0000002", "not-a-number")
    check("non-numeric RMS dropped", evs == [])
    evs = feed._adapt("some/other/topic", 1)
    check("unknown topic dropped", evs == [])


def test_num():
    print("== _num scalar extraction ==")
    check("_num float", _num(4.5) == 4.5)
    check("_num int", _num(4) == 4.0)
    check("_num str float", _num("0.0045821") == 0.0045821)
    check("_num str junk -> None", _num("abc") is None)
    check("_num bool -> None", _num(True) is None)
    check("_num dict value", _num({"value": 3.2}) == 3.2)
    check("_num dict rms", _num({"rms": 1.1}) == 1.1)
    check("_num dict junk -> None", _num({"foo": "bar"}) is None)
    check("_num None -> None", _num(None) is None)


def test_recorder_pattern_isolation():
    print("== recorder pattern isolation (hero arc untouched) ==")
    bus = events.get_bus()
    cfg = Settings()
    # one store per recorder so we can prove the patterns never cross
    hero_store = db.MemoryStore(bridge="z24")
    live_store = db.MemoryStore(bridge="live-demo")
    hero_token = db.attach_recorder(cfg, bus, hero_store)            # bridge/z24/#
    live_token = db.attach_recorder(cfg, bus, live_store, pattern="bridge/live-demo/#")

    # a live-demo accel event persists via the live recorder only
    bus.publish("bridge/live-demo/accel",
                {"bridge": "live-demo", "node": 1, "ts": 100.0, "rms": 0.0045,
                 "flag": 0, "source": "public-mosquitto"})
    check("live accel persisted to live store", len(live_store.rms) == 1)
    check("live accel NOT in hero store", len(hero_store.rms) == 0)
    if live_store.rms:
        _, node, rms, _ = live_store.rms[0]
        check("live row node/rms", node == 1 and abs(rms - 0.0045) < 1e-9)

    # a hero z24 accel event must stay in the hero store (arc untouched)
    bus.publish("bridge/z24/accel",
                {"bridge": "z24", "node": 6, "ts": 101.0, "rms": 0.02, "flag": 0})
    check("hero z24 persisted to hero store", len(hero_store.rms) == 1)
    check("hero z24 NOT in live store", len(live_store.rms) == 1)

    # live-demo telemetry flows but adds no rows (suffix check, not persisted)
    bus.publish("bridge/live-demo/telemetry",
                {"bridge": "live-demo", "metric": "temperature", "value": 21.0})
    check("live telemetry not persisted", len(live_store.rms) == 1)

    bus.unsubscribe(hero_token)
    bus.unsubscribe(live_token)


def main():
    test_adapt_namespaces()
    test_num()
    test_recorder_pattern_isolation()
    print()
    print(f"{'=' * 48}")
    print(f" live-feed unit: {PASS} passed, {FAIL} failed")
    if FAILURES:
        for f in FAILURES:
            print(f"   FAILED: {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
