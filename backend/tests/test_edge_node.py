"""
Real-hardware edge-node gate — ESP32 monitor + API + manifest honesty.

Covers the LIVE-badge data path without needing the physical board: an
EdgeNodeMonitor listens on the shared event bus (the same route the backend's
MQTT subscriber feeds when the real ESP32 publishes bridge/esp32-1/accel), and
we assert the status/API/manifest surface the honest labels — real hardware,
self-test BIST accel (NO accelerometer attached), real RSSI/heap/uptime,
and never fused into the z24 BHI.

Run:  python backend/tests/test_edge_node.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import channel_models as cm  # noqa: E402
from app import edge_node as edge_mod  # noqa: E402
from app.config import settings  # noqa: E402
from app.events import get_bus  # noqa: E402

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


def _accel(rms: float = 0.035, flag: int = 0) -> dict:
    return {"bridge": edge_mod.EDGE_BRIDGE, "node": 1, "ts": time.time(), "fs": 100,
            "samples": [0.01] * 100, "rms": rms, "flag": flag,
            "signal_kind": "self-test-bist", "source": edge_mod.EDGE_BRIDGE,
            "rssi": -61, "heap": 28512, "uptime_s": 123, "fw": "vitish-edge-esp32-0.1"}


def test_monitor_state() -> None:
    print("[1] edge-node monitor state")
    bus = get_bus()
    mon = edge_mod.EdgeNodeMonitor(bus)
    mon.start()
    try:
        # offline before any event
        st = mon.status()
        check("offline before first message", st["online"] is False)
        check("enabled", st["enabled"] is True)
        check("bridge id", st["bridge"] == edge_mod.EDGE_BRIDGE)
        check("hero bridge untouched flag", st["hero_bridge_untouched"] is True)

        bus.publish(f"bridge/{edge_mod.EDGE_BRIDGE}/accel", _accel(), source="test")
        bus.publish(f"bridge/{edge_mod.EDGE_BRIDGE}/status",
                    {"bridge": edge_mod.EDGE_BRIDGE, "node": 1, "online": True,
                     "fw": "vitish-edge-esp32-0.1", "rssi": -60}, source="test")
        time.sleep(0.05)
        st = mon.status()
        check("online after accel", st["online"] is True)
        check("received counted", st["received"] == 2)
        check("rssi captured", st["rssi_dbm"] == -60)
        check("heap captured", st["heap_bytes"] == 28512)
        check("uptime captured", st["uptime_s"] == 123)
        check("fw captured", st["fw"] == "vitish-edge-esp32-0.1")
        check("signal_kind honest", st["signal_kind"] == "self-test-bist")
        check("last accel rms", st["accel"]["rms"] == 0.035)
        check("last accel flag", st["accel"]["flag"] == 0)
        check("recent rms ring", len(st["recent_rms"]) == 1)

        # honesty labels
        h = st["honesty"]
        check("honesty.real_hardware", h["real_hardware"] is True)
        check("honesty names no accelerometer",
              "no accelerometer" in h["accel_is"])
        check("honesty lists real measured", "WiFi RSSI (dBm)" in h["real_measured"]
              and "uptime (s)" in h["real_measured"])

        # stale -> offline
        with mon._lock:
            mon.last_seen = time.time() - mon.stale_s - 1.0
        st = mon.status()
        check("offline after stale window", st["online"] is False)
        check("last_seen_ago reported", st["last_seen_ago_s"] is not None)
    finally:
        mon.stop()


def test_api_surface() -> None:
    print("[2] FastAPI edge-node surface (TestClient)")
    from fastapi.testclient import TestClient
    from app.api import create_app

    bus = get_bus()
    mon = edge_mod.EdgeNodeMonitor(bus)
    mon.start()
    edge_mod.set_edge_monitor(mon)
    try:
        client = TestClient(create_app())

        r = client.get(f"/api/bridge/{edge_mod.EDGE_BRIDGE}/state")
        check("state endpoint 200", r.status_code == 200)
        js = r.json()
        check("state id", js["id"] == edge_mod.EDGE_BRIDGE)
        check("state live", js["live"] is True)
        check("state hardware label", js["hardware"].startswith("ESP-01S") or
              js["hardware"].startswith("ESP32"))

        bus.publish(f"bridge/{edge_mod.EDGE_BRIDGE}/accel", _accel(), source="test")
        time.sleep(0.05)
        r = client.get(f"/api/bridge/{edge_mod.EDGE_BRIDGE}/history?metric=rms")
        check("history rms 200", r.status_code == 200)
        check("history rms data", len(r.json()["data"]) == 1)
        r = client.get(f"/api/bridge/{edge_mod.EDGE_BRIDGE}/history?metric=bhi")
        check("history bhi rejected", r.status_code == 400)

        r = client.get("/api/manifest")
        check("manifest 200", r.status_code == 200)
        en = r.json().get("edge_node", {})
        check("manifest edge_node present", en.get("bridge") == edge_mod.EDGE_BRIDGE)
        check("manifest edge_node real_hardware", en.get("real_hardware") is True)
        check("manifest edge_node honesty note",
              "no accelerometer" in en.get("note", "") or
              "SELF-TEST" in en.get("note", ""))
        check("manifest edge_node status online", en["status"]["online"] is True)
    finally:
        edge_mod.set_edge_monitor(None)
        mon.stop()


def test_manifest_no_monitor() -> None:
    print("[3] manifest without an edge monitor")
    m = cm.build_manifest(settings, "z24-replay", live_active=False,
                          edge_status=None)
    check("manifest builds without edge", m["edge_node"]["bridge"] == "esp32-1")
    check("empty edge status default", m["edge_node"]["status"] == {})


def main() -> int:
    test_monitor_state()
    test_api_surface()
    test_manifest_no_monitor()
    print(f"\nedge-node gate: {PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILURES:")
        for f in FAILURES:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
