"""
VITISH 2026 · PS#99 SHM — backend smoke test (no broker / no Postgres required).

Run from backend/:  python tests/smoke_test.py

Exercises the pieces that can run without infrastructure: contract conformance
of simulator payloads, synthetic fallback, anomaly scoring, the damage injector
ramp, event bus, memory-store persistence + reload, BHI math, WebSocket
broadcast, the FastAPI surface (via TestClient) and the demo driver beat list.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import numpy as np

from app import contract, db, events
from app.anomaly import get_anomaly, reset_anomaly_baseline
from app.config import Settings, settings
from app.demo_driver import BEATS, main as demo_main
from app.fusion import FusionService
from app.mqtt_client import Publisher, emit
from app.simulator import (
    DamageInjector,
    Simulator,
    SyntheticPlayer,
    pink_noise,
)
from app.ws_bridge import WSBridge

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


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------
class FakePublisher(Publisher):
    """In-memory publisher: records what would go to MQTT, never connects."""

    def __init__(self):
        self.connected = threading.Event()
        self.connected.set()
        self.accel = []
        self.bhi = []
        self.alerts = []
        self.status = []
        self.all_topics = []

    def start(self):
        pass

    def stop(self):
        pass

    def wait_connected(self, timeout=5.0):
        return True

    def publish(self, topic, payload, qos=1):
        self.all_topics.append((topic, payload))
        if topic.endswith("/bhi"):
            self.bhi.append(payload)
        elif topic.endswith("/alert"):
            self.alerts.append(payload)
        elif topic.endswith("/status"):
            self.status.append(payload)
        elif topic.endswith("/accel"):
            self.accel.append(payload)
        return True

    def publish_accel(self, **kw):
        self.accel.append(kw)
        return True

    def publish_bhi(self, **kw):
        self.bhi.append(kw)
        return True

    def publish_alert(self, **kw):
        self.alerts.append(kw)
        return True

    def publish_status(self, **kw):
        self.status.append(kw)
        return True


# ---------------------------------------------------------------------------
# 1. contract math
# ---------------------------------------------------------------------------
def test_contract():
    print("[1] BHI contract math")
    b = contract.compute_bhi(0.10, 0.12, 0.19)
    check("baseline BHI ~87", abs(b - 87.0) < 0.2, f"got {b}")
    check("87 is GREEN", contract.state_for(b) == "GREEN")
    b2 = contract.compute_bhi(0.55, 0.90, 0.40)
    check("damage BHI RED", contract.state_for(b2) == "RED" and b2 < 50, f"got {b2}")
    check("state_for(70)=GREEN", contract.state_for(70.0) == "GREEN")
    check("state_for(69.9)=AMBER", contract.state_for(69.9) == "AMBER")
    check("state_for(50)=AMBER", contract.state_for(50.0) == "AMBER")
    check("state_for(49.9)=RED", contract.state_for(49.9) == "RED")


# ---------------------------------------------------------------------------
# 2. synthetic signals + anomaly
# ---------------------------------------------------------------------------
def test_synthetic():
    print("[2] synthetic signals + anomaly scoring")
    hp = SyntheticPlayer("healthy", [6, 7, 8], seed=1)
    rp = SyntheticPlayer("rupture", [6, 7, 8], seed=2)
    h = hp.current_window(6)
    r = rp.current_window(6)
    check("healthy window 100 samples", h.shape == (100,))
    check("rupture window 100 samples", r.shape == (100,))
    hrms, rrms = float(np.sqrt(np.mean(h ** 2))), float(np.sqrt(np.mean(r ** 2)))
    check("rupture RMS >> healthy RMS", rrms > 3 * hrms, f"{hrms:.4f} vs {rrms:.4f}")
    hp.tick()
    h2 = hp.current_window(6)
    check("tick advances window", not np.allclose(h, h2))

    reset_anomaly_baseline()
    hw = np.concatenate([hp.current_window(6) for _ in range(11)])[:1024]
    s0, u0 = get_anomaly(hw)
    t = np.arange(1024) / 100.0
    tonal = hw + 0.5 * np.sin(2 * np.pi * 4 * t) + 0.25 * np.sin(2 * np.pi * 8 * t)
    s1, u1 = get_anomaly(tonal)
    check("healthy score low (<0.35)", s0 < 0.35, f"{s0:.3f}")
    check("rupture tonal score much higher", s1 > s0 + 0.35, f"{s0:.3f} -> {s1:.3f}")
    check("score bounded [0,1]", 0.0 <= s1 <= 1.0)
    check("uncertainty bounded [0,0.4]", 0.0 <= u1 <= 0.4)


# ---------------------------------------------------------------------------
# 3. damage injector ramp
# ---------------------------------------------------------------------------
def test_injector():
    print("[3] damage injector smooth ramp")
    hp = SyntheticPlayer("healthy", [6], seed=1)
    rp = SyntheticPlayer("rupture", [6], seed=2)
    inj = DamageInjector(hp, rp, settings, rng_seed=3)
    inj.set_scenario("rupture")
    inj.ramp_s = settings.ramp_s  # default 10s
    # simulate a ramp: current_window then tick at high speed via time travel
    # (we can't time-travel; instead directly probe _alpha_now by faking switch_t)
    inj.switch_t = time.monotonic() - 5.0   # 5 s into a 10 s ramp
    inj.impact_t0 = None
    w = inj.current_window(6)
    check("mid-ramp alpha ~0.5", abs(inj.alpha - 0.5) < 0.2, f"{inj.alpha:.3f}")
    inj.switch_t = time.monotonic() - 20.0  # ramp complete
    w2 = inj.current_window(6)
    check("ramp completes alpha=1", abs(inj.alpha - 1.0) < 1e-6, f"{inj.alpha:.3f}")
    check("rupture RMS high after ramp",
          float(np.sqrt(np.mean(w2 ** 2))) > float(np.sqrt(np.mean(w ** 2))))
    try:
        inj.set_scenario("nonsense")
        check("invalid scenario rejected", False)
    except ValueError:
        check("invalid scenario rejected", True)
    # impact pulse fires once on rupture onset
    inj2 = DamageInjector(hp, rp, settings, rng_seed=4)
    inj2.set_scenario("rupture")
    inj2.impact_t0 = time.monotonic()
    wp = inj2.current_window(6)
    check("impact pulse on onset", float(np.sqrt(np.mean(wp ** 2))) > 0.3)
    # runaway flag
    inj2._rms_ema = 0.05
    check("flag low rms=0", inj2.rms_flag(0.05) == 0)
    check("flag high rms=1", inj2.rms_flag(0.6) == 1)


# ---------------------------------------------------------------------------
# 4. simulator end-to-end (synthetic, offline)
# ---------------------------------------------------------------------------
def test_simulator():
    print("[4] simulator synthetic end-to-end (offline)")
    bus = events.get_bus()
    pub = FakePublisher()
    sim = Simulator(settings, pub, bus=bus, synthetic=True, scenario="healthy",
                    loops=0, rate=200.0)
    check("data source synthetic", sim.data_source == "synthetic")
    t = threading.Thread(target=sim.run, daemon=True)
    t.start()
    time.sleep(0.25)
    # control the injector through the bus WHILE the sim is running
    bus.publish("control/cmd", {"cmd": "scenario", "scenario": "rupture"})
    time.sleep(0.1)
    check("control/cmd switches scenario", sim.injector.scenario == "rupture")
    sim.stop()
    t.join(timeout=3.0)
    check("simulator published accel", len(pub.accel) > 0)
    if pub.accel:
        p = pub.accel[0]
        errors = contract.validate_accel(p)
        check("accel payload conforms to contract", errors == [], str(errors))
        check("node in {6,7,8}", p["node"] in (6, 7, 8))
        check("100 samples", len(p["samples"]) == 100)
        check("fs=100", p["fs"] == 100)
        check("rms > 0", p["rms"] > 0)
        check("msg_id present", "msg_id" in p)


# ---------------------------------------------------------------------------
# 5. event bus
# ---------------------------------------------------------------------------
def test_bus():
    print("[5] event bus pub/sub")
    bus = events.get_bus()
    got = []
    tok = bus.subscribe("bridge/z24/#", lambda t, p: got.append((t, p)))
    tok2 = bus.subscribe("control/cmd", lambda t, p: got.append(("CONTROL", p)))
    bus.publish("bridge/z24/accel", {"x": 1})
    bus.publish("control/cmd", {"cmd": "scenario"})
    check("wildcard # matches accel", any(t == "bridge/z24/accel" for t, _ in got))
    check("exact control topic", any(t == "CONTROL" for t, _ in got))
    bus.unsubscribe(tok)
    n = len(got)
    bus.publish("bridge/z24/accel", {"x": 2})
    check("unsubscribe works", len(got) == n)
    bus.unsubscribe(tok2)
    # '+'-level matching
    got2 = []
    tok3 = bus.subscribe("bridge/+/bhi", lambda t, p: got2.append(t))
    bus.publish("bridge/z24/bhi", {"bhi": 90})
    bus.publish("bridge/z24/accel", {})
    check("+ matches one level", got2 == ["bridge/z24/bhi"])


# ---------------------------------------------------------------------------
# 6. memory store + persistence
# ---------------------------------------------------------------------------
def test_store():
    print("[6] memory store + JSON persistence")
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "state_cache.json"
    st = db.MemoryStore(cache_path=tmp)
    st.insert_accel(node=7, ts=1.0, rms=0.05, flag=0)
    st.insert_accel(node=8, ts=1.1, rms=0.06, flag=0)
    st.insert_bhi(ts=1.0, bhi=87.0, u=3.0, cv=0.1, vib=0.12, load=0.19, state="GREEN")
    st.insert_alert(ts=1.0, severity="critical", source="fusion", text="x", recommendation="y")
    st.close()

    st2 = db.MemoryStore(cache_path=tmp)  # reload
    rms = st2.recent_rms("z24", 10)
    bhi = st2.recent_bhi("z24", 10)
    al = st2.recent_alerts("z24", 10)
    check("rms persisted+reloaded", len(rms) == 2 and rms[0]["rms"] == 0.05)
    check("bhi persisted+reloaded", len(bhi) == 1 and bhi[0]["bhi"] == 87.0)
    check("alerts persisted+reloaded", len(al) == 1 and al[0]["text"] == "x")
    cs = st2.current_state("z24")
    check("current_state bhi", cs["bhi"] == 87.0)
    check("current_state nodes", "7" in cs["nodes"] and "8" in cs["nodes"])
    check("current_state source", cs["source"] == "memory")
    st2.close()


# ---------------------------------------------------------------------------
# 7. fusion BHI lifecycle
# ---------------------------------------------------------------------------
def test_fusion():
    print("[7] fusion BHI lifecycle")
    bus = events.get_bus()
    pub = FakePublisher()
    st = db.MemoryStore(cache_path=None)
    fus = FusionService(settings, bus, st, pub)
    fus.start()
    # feed healthy synthetic windows through the bus
    hp = SyntheticPlayer("healthy", [6, 7, 8], seed=1)
    for _ in range(12):
        for node in (6, 7, 8):
            w = hp.current_window(node)
            bus.publish("bridge/z24/accel", {
                "bridge": "z24", "node": node, "ts": time.time(),
                "samples": [float(x) for x in w], "fs": 100,
            })
        hp.tick()
    time.sleep(0.2)
    check("fusion emits BHI ~1/s", len(pub.bhi) >= 1)
    if pub.bhi:
        p = pub.bhi[-1]
        check("BHI in healthy range 80-95", 80 <= p["bhi"] <= 95, str(p))
        check("BHI state GREEN", p["state"] == "GREEN")
        check("BHI payload contract keys", all(k in p for k in
              ("bridge", "ts", "bhi", "u", "cv", "vib", "load", "state")))
    # escalate evidence + scenario
    bus.publish("control/cmd", {"cmd": "cv", "value": 0.55})
    bus.publish("control/cmd", {"cmd": "load", "value": 0.40})
    bus.publish("control/cmd", {"cmd": "scenario", "scenario": "rupture"})
    rp = SyntheticPlayer("rupture", [6, 7, 8], seed=2)
    for _ in range(12):
        for node in (6, 7, 8):
            w = rp.current_window(node)
            bus.publish("bridge/z24/accel", {
                "bridge": "z24", "node": node, "ts": time.time(),
                "samples": [float(x) for x in w], "fs": 100,
            })
        rp.tick()
    # BHI publishes at most once per second (contract cadence); the burst feed
    # finished inside the throttle window, so drive one publish to assert the
    # fused outcome for the current internal state.
    time.sleep(0.3)
    check("fusion cv updated", fus.cv == 0.55, str(fus.cv))
    check("fusion load updated", fus.load == 0.40, str(fus.load))
    check("fusion vib rises with rupture", fus.vib > 0.3, str(fus.vib))
    fus.publish_bhi()
    last = pub.bhi[-1]
    check("fusion BHI drops on damage", last["bhi"] < 65, str(last))
    check("state becomes non-GREEN", last["state"] in ("AMBER", "RED"), str(last))
    fus.stop()


# ---------------------------------------------------------------------------
# 8. emit fallback (no broker -> event bus)
# ---------------------------------------------------------------------------
def test_emit():
    print("[8] emit MQTT/bus fallback")
    bus = events.get_bus()
    got = []
    tok = bus.subscribe("bridge/z24/status", lambda t, p: got.append(p))
    # broker 'down': connected flag clear -> falls back to bus
    pub_off = FakePublisher()
    pub_off.connected.clear()
    emit("bridge/z24/status", {"online": True}, pub_off, bus=bus)
    check("emit fallback lands on bus", len(got) == 1)
    # broker 'up': publishes only via MQTT, no bus duplicate
    pub_on = FakePublisher()
    pub_on.connected.set()
    emit("bridge/z24/status", {"online": False}, pub_on, bus=bus)
    check("no duplicate when broker up", len(got) == 1)
    bus.unsubscribe(tok)


# ---------------------------------------------------------------------------
# 9. WS bridge broadcast
# ---------------------------------------------------------------------------
def test_ws():
    print("[9] WebSocket bridge broadcast")
    bus = events.get_bus()
    tcfg = Settings(ws_port=8976)
    ws = WSBridge(tcfg, bus)
    ws.start()
    time.sleep(0.3)

    async def run():
        import websockets
        async with websockets.connect("ws://127.0.0.1:8976") as c:
            hello = json.loads(await c.recv())
            assert hello["topic"] == "hello", hello
            # bridge replays the current storyboard scenario on connect
            snap = json.loads(await c.recv())
            assert snap["topic"] == "control/cmd", snap
            bus.publish("bridge/z24/accel",
                        {"bridge": "z24", "node": 6, "samples": [1.0] * 100, "ts": 1.0})
            msg = json.loads(await asyncio.wait_for(c.recv(), timeout=3.0))
            return hello, snap, msg

    hello, snap, msg = asyncio.new_event_loop().run_until_complete(run())
    check("ws hello", hello.get("topic") == "hello")
    check("ws scenario snapshot on connect",
          snap.get("cmd") == "scenario" and snap.get("scenario") == "healthy")
    check("ws fanout envelope topic", msg.get("topic") == "bridge/z24/accel")
    check("ws fanout carries payload", msg.get("node") == 6 and len(msg.get("samples", [])) == 100)

    # scenario cmd is forwarded live AND replayed to a fresh client as catch-up
    bus.publish("control/cmd", {"cmd": "scenario", "scenario": "rupture", "source": "test"})

    async def run2():
        import websockets
        async with websockets.connect("ws://127.0.0.1:8976") as c:
            await c.recv()  # hello
            snap2 = json.loads(await c.recv())
            return snap2

    snap2 = asyncio.new_event_loop().run_until_complete(run2())
    check("ws scenario catch-up after change",
          snap2.get("cmd") == "scenario" and snap2.get("scenario") == "rupture")
    ws.stop()


# ---------------------------------------------------------------------------
# 10. FastAPI surface
# ---------------------------------------------------------------------------
def test_api():
    print("[10] FastAPI surface (TestClient)")
    db.reset_store()
    db.get_store(settings, prefer="memory")  # cache a memory store, no PG attempt
    from fastapi.testclient import TestClient
    import app.api as api_mod
    app = api_mod.create_app()
    client = TestClient(app)

    r = client.get("/health")
    check("GET /health 200", r.status_code == 200)
    hb = r.json()
    check("health broker reachable flag", "reachable" in hb["broker"])

    r = client.get("/api/bridges")
    check("GET /api/bridges 200", r.status_code == 200)
    j = r.json()
    check("50 bridges (1 hero + 49)", j["count"] == 50, f"got {j['count']}")
    check("hero is z24", j["hero"]["id"] == "z24")
    regs = [b for b in j["bridges"] if not b["hero"]]
    check("49 regulators", len(regs) == 49)
    check("regulator has real location", all("city" in b and b["lat"] for b in regs))

    r = client.get("/api/bridges/geojson")
    check("geojson 50 features", r.status_code == 200 and len(r.json()["features"]) == 50)

    r = client.get("/api/bridge/z24/state")
    check("hero state 200", r.status_code == 200)
    check("hero state has bhi", r.json().get("bhi") is not None)

    r = client.get("/api/bridge/z24/history?metric=bhi&limit=10")
    check("hero bhi history 200", r.status_code == 200 and "data" in r.json())
    r = client.get("/api/bridge/z24/history?metric=rms&limit=10")
    check("hero rms history 200", r.status_code == 200)
    r = client.get("/api/bridge/z24/history?metric=nope")
    check("bad metric -> 400", r.status_code == 400)

    r = client.get("/api/bridge/reg-01/history?metric=bhi&limit=5")
    check("regulator history 200", r.status_code == 200 and len(r.json()["data"]) == 5)
    r = client.get("/api/bridge/reg-01/state")
    check("regulator state 200", r.status_code == 200 and r.json()["bhi"] > 0)
    r = client.get("/api/bridge/nope/state")
    check("unknown bridge -> 404", r.status_code == 404)

    # demo scenario control reaches the bus
    got = []
    tok = events.get_bus().subscribe("control/cmd", lambda t, p: got.append(p))
    r = client.post("/api/demo/scenario", json={"scenario": "rupture"})
    check("POST scenario 200", r.status_code == 200 and r.json()["ok"] is True)
    check("scenario lands on bus", got and got[-1]["scenario"] == "rupture")
    r = client.post("/api/demo/scenario", json={"scenario": "bogus"})
    check("invalid scenario -> 422", r.status_code == 422)
    events.get_bus().unsubscribe(tok)


# ---------------------------------------------------------------------------
# 11. demo driver
# ---------------------------------------------------------------------------
def test_demo():
    print("[11] demo driver beat list + --json")
    check("beats sorted ascending", all(BEATS[i]["t"] <= BEATS[i + 1]["t"]
                                        for i in range(len(BEATS) - 1)))
    check("crack beat before bhi-drop", BEATS[2]["t"] < BEATS[4]["t"])
    names = [b["name"] for b in BEATS]
    check("has copilot recommendation beat", "copilot-recommendation" in names)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = demo_main(["--json"])
    check("demo_main --json rc=0", rc == 0)
    try:
        out = json.loads(buf.getvalue())
        check("--json is valid JSON", isinstance(out, list) and len(out) == len(BEATS))
    except json.JSONDecodeError:
        check("--json is valid JSON", False)
    # driver fires commands/alerts against a fake publisher offline
    bus = events.get_bus()
    pub = FakePublisher()
    from app.demo_driver import DemoDriver
    d = DemoDriver(settings, bus, pub, timeline="demo", speed=1000.0)
    # fire all beats immediately (speed huge -> sleeps skipped)
    d.stop()  # not needed for _fire; call directly
    d._fire(BEATS[2], 2)
    d._fire(BEATS[3], 3)
    d._fire(BEATS[4], 4)
    check("crack beat sends cv cmd", any(p.get("cmd") == "cv" for _, p in
                                         [(None, a["payload"]) for a in BEATS[2]["actions"]]))
    check("bhi-drop sends alerts", len(pub.alerts) >= 1)
    if pub.alerts:
        a = pub.alerts[-1]
        check("alert is critical fusion", a.get("severity") == "critical"
              and a.get("source") == "fusion")
    # rupture cmd must land on the bus as a control event
    got = []
    tok = bus.subscribe("control/cmd", lambda t, p: got.append(p))
    d._fire(BEATS[3], 3)  # vibration-anomaly beat -> scenario rupture
    check("rupture cmd published to bus", any(p.get("scenario") == "rupture" for p in got))
    bus.unsubscribe(tok)


# ---------------------------------------------------------------------------
def main():
    tests = [test_contract, test_synthetic, test_injector, test_simulator,
             test_bus, test_store, test_fusion, test_emit, test_ws, test_api,
             test_demo]
    for t in tests:
        try:
            t()
        except Exception as exc:
            global FAIL
            FAIL += 1
            FAILURES.append(t.__name__)
            import traceback
            print(f"  [ERROR] {t.__name__} raised: {exc}")
            traceback.print_exc()
    print()
    print(f"== smoke test: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
