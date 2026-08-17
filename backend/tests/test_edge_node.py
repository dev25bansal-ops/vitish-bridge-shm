"""
Real-hardware edge-node gate — ESP32 + ESP-01S monitor + API + manifest honesty.

Covers the LIVE-badge data path without needing the physical boards: an
EdgeNodeMonitor listens on the shared event bus (the same route the backend's
MQTT subscriber feeds when the real ESP32 / ESP-01S node publishes
bridge/<id>/accel), and we assert the status/API/manifest surface honest labels
— real hardware, self-test BIST accel (NO accelerometer attached), real
RSSI/heap/uptime, and never fused into the z24 BHI.

The monitor watches EVERY id in ``edge_mod.EDGE_BRIDGES`` (default esp32-1 +
esp01-1), so a stock-flashed ESP-01S is NOT silently ignored: the S8 fix.
A separate test publishes bridge/esp01-1/accel and asserts the monitor + API
report the ESP-01S node with its own honest hardware/fw labels.

Run:  python backend/tests/test_edge_node.py
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import channel_models as cm  # noqa: E402
from app import db  # noqa: E402
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


def _accel(bridge: str, fw: str, rms: float = 0.035, flag: int = 0) -> dict:
    return {"bridge": bridge, "node": 1, "ts": time.time(), "fs": 100,
            "samples": [0.01] * 100, "rms": rms, "flag": flag,
            "signal_kind": "self-test-bist", "source": bridge,
            "rssi": -61, "heap": 28512, "uptime_s": 123, "fw": fw}


def test_monitor_state() -> None:
    print("[1] edge-node monitor state (primary slot)")
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

        fw = "vitish-edge-esp32-0.1"
        bus.publish(f"bridge/{edge_mod.EDGE_BRIDGE}/accel",
                    _accel(edge_mod.EDGE_BRIDGE, fw), source="test")
        bus.publish(f"bridge/{edge_mod.EDGE_BRIDGE}/status",
                    {"bridge": edge_mod.EDGE_BRIDGE, "node": 1, "online": True,
                     "fw": fw, "rssi": -60}, source="test")
        time.sleep(0.05)
        st = mon.status()
        check("online after accel", st["online"] is True)
        check("received counted", st["received"] == 2)
        check("rssi captured", st["rssi_dbm"] == -60)
        check("heap captured", st["heap_bytes"] == 28512)
        check("uptime captured", st["uptime_s"] == 123)
        check("fw captured", st["fw"] == fw)
        check("signal_kind honest", st["signal_kind"] == "self-test-bist")
        check("last accel rms", st["accel"]["rms"] == 0.035)
        check("last accel flag", st["accel"]["flag"] == 0)
        check("recent rms ring", len(st["recent_rms"]) == 1)
        # default status() picks the most-recently-active bridge = this slot
        check("default status primary", st["bridge"] == edge_mod.EDGE_BRIDGE)

        # honesty labels
        h = st["honesty"]
        check("honesty.real_hardware", h["real_hardware"] is True)
        check("honesty names no accelerometer",
              "no accelerometer" in h["accel_is"])
        check("honesty lists real measured", "WiFi RSSI (dBm)" in h["real_measured"]
              and "uptime (s)" in h["real_measured"])

        # stale -> offline (per-bridge state)
        with mon._lock:
            mon._state[edge_mod.EDGE_BRIDGE]["last_seen"] = \
                time.time() - mon.stale_s - 1.0
        st = mon.status()
        check("offline after stale window", st["online"] is False)
        check("last_seen_ago reported", st["last_seen_ago_s"] is not None)
    finally:
        mon.stop()


def test_esp01_not_silently_ignored() -> None:
    """S8 fix: a stock-flashed ESP-01S (bridge esp01-1) is monitored and
    reported with its OWN honest hardware/fw labels — never treated as an
    ESP32, and never dropped because the monitor only watched esp32-1."""
    print("[2] S8 — ESP-01S slot (esp01-1) not silently ignored")
    if "esp01-1" not in edge_mod.EDGE_BRIDGES:
        check("esp01-1 in EDGE_BRIDGES",
              False, f"(configured set={edge_mod.EDGE_BRIDGES})")
        return
    bus = get_bus()
    mon = edge_mod.EdgeNodeMonitor(bus)
    mon.start()
    try:
        fw = "vitish-edge-esp01-0.1"
        bus.publish("bridge/esp01-1/accel", _accel("esp01-1", fw), source="test")
        bus.publish("bridge/esp01-1/status",
                    {"bridge": "esp01-1", "node": 1, "online": True,
                     "fw": fw, "rssi": -58}, source="test")
        time.sleep(0.05)

        st = mon.status(bridge="esp01-1")
        check("esp01-1 monitored", st is not None)
        if st is None:
            return
        check("esp01-1 online", st["online"] is True)
        check("esp01-1 received counted", st["received"] == 2)
        check("esp01-1 fw captured", st["fw"] == fw)
        check("esp01-1 honest hardware label", "ESP-01S" in st["hardware"])
        check("esp01-1 signal_kind honest", st["signal_kind"] == "self-test-bist")

        # the primary slot stays untouched until it publishes
        st_primary = mon.status(bridge="esp32-1")
        check("esp32-1 untouched by esp01 traffic",
              st_primary is not None and st_primary["received"] == 0)
    finally:
        mon.stop()


def test_recorder_captures_esp01() -> None:
    """S8 fix, recorder leg: the edge recorder subscribes to EVERY id in
    EDGE_BRIDGES, so an esp01-1 accel row is persisted (it was silently dropped
    when the recorder only watched esp32-1).  The bridge-identity boundary
    (ROADMAP line 38) still drops a row that lies about its bridge on the topic."""
    print("[3] S8 — recorder persists esp01-1 rows (per-bridge patterns)")
    if "esp01-1" not in edge_mod.EDGE_BRIDGES:
        check("esp01-1 in EDGE_BRIDGES",
              False, f"(configured set={edge_mod.EDGE_BRIDGES})")
        return
    bus = get_bus()
    tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False,
                                      mode="w", encoding="utf-8")
    tmp.close()
    store = db.MemoryStore(bridge="esp01-1", cache_path=Path(tmp.name))
    tok = db.attach_recorder(settings, bus, store, pattern="bridge/esp01-1/#")
    try:
        bus.publish("bridge/esp01-1/accel",
                    _accel("esp01-1", "vitish-edge-esp01-0.1"), source="test")
        time.sleep(0.05)
        rows = store.recent_rms("esp01-1", 1)
        check("recorder persisted esp01-1 row", len(rows) == 1)
        check("recorder row rms", rows and abs(rows[0]["rms"] - 0.035) < 1e-6)

        # inconsistent row on this topic (claims esp32-1) must be dropped
        bus.publish("bridge/esp01-1/accel",
                    _accel("esp32-1", "vitish-edge-esp32-0.1"), source="test")
        time.sleep(0.05)
        rows = store.recent_rms("esp01-1", 2)
        check("recorder dropped bridge-mismatched row", len(rows) == 1)
    finally:
        bus.unsubscribe(tok)
        store.close()
        Path(tmp.name).unlink(missing_ok=True)


def test_api_surface() -> None:
    print("[4] FastAPI edge-node surface (TestClient)")
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
        # item 15 LIVE-badge gating: before ANY packet is measured, the edge
        # bridge must NOT claim live: True (firmware committed, board not
        # flashed/bench-tested), and the off-line state must say why.
        check("state NOT live before any measured packet",
              js["live"] is False, f"live={js['live']!r}")
        check("state off-line labeled honestly",
              "not flashed" in js.get("live_label", "") or
              "OFF-LINE" in js.get("live_label", "") or
              "no measured packet" in js.get("live_label", ""),
              f"live_label={js.get('live_label')!r}")
        check("state hardware label", js["hardware"].startswith("ESP-01S") or
              js["hardware"].startswith("ESP32"))

        bus.publish(f"bridge/{edge_mod.EDGE_BRIDGE}/accel",
                    _accel(edge_mod.EDGE_BRIDGE, "vitish-edge-esp32-0.1"),
                    source="test")
        time.sleep(0.05)
        r = client.get(f"/api/bridge/{edge_mod.EDGE_BRIDGE}/state")
        js = r.json()
        check("state live after a real packet measured",
              js["live"] is True, f"live={js['live']!r}")
        check("state online after packet", js["online"] is True)
        check("state still honest on accel content",
              js.get("signal_kind") == "self-test-bist" and
              "no accelerometer" in js.get("honesty", {}).get("accel_is", ""))
        r = client.get(f"/api/bridge/{edge_mod.EDGE_BRIDGE}/history?metric=rms")
        check("history rms 200", r.status_code == 200)
        check("history rms data", len(r.json()["data"]) == 1)
        r = client.get(f"/api/bridge/{edge_mod.EDGE_BRIDGE}/history?metric=bhi")
        check("history bhi rejected", r.status_code == 400)

        # esp01-1 API surface — honest ESP-01S labels (S8)
        if "esp01-1" in edge_mod.EDGE_BRIDGES:
            bus.publish("bridge/esp01-1/accel",
                        _accel("esp01-1", "vitish-edge-esp01-0.1"),
                        source="test")
            time.sleep(0.05)
            r = client.get("/api/bridge/esp01-1/state")
            check("esp01-1 state 200", r.status_code == 200)
            js = r.json()
            check("esp01-1 state name", js["name"] == "ESP-01S edge node")
            check("esp01-1 state hardware", "ESP-01S" in js["hardware"])
            check("esp01-1 state online", js["online"] is True)
            r = client.get("/api/bridge/esp01-1/history?metric=rms")
            check("esp01-1 history rms 200", r.status_code == 200)
            check("esp01-1 history rms data", len(r.json()["data"]) == 1)

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
    print("[5] manifest without an edge monitor")
    m = cm.build_manifest(settings, "z24-replay", live_active=False,
                          edge_status=None)
    check("manifest builds without edge", m["edge_node"]["bridge"] == "esp32-1")
    check("empty edge status default", m["edge_node"]["status"] == {})


def main() -> int:
    test_monitor_state()
    test_esp01_not_silently_ignored()
    test_recorder_captures_esp01()
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
