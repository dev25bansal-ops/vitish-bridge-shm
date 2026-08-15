"""
D2-gate — DemoDriver beat-timing regression (ROADMAP line 57).

Drives the REAL ``DemoDriver.run()`` (not just ``_fire``) end-to-end against the
event bus + a FakePublisher and pins:

  1. The full 7-beat storyboard sequence fires in order
     (healthy-baseline -> monitoring-status -> crack-detected ->
      vibration-anomaly -> bhi-drop -> copilot-recommendation -> hold).
  2. The exact bus commands / alerts / status payloads each beat fires
     (cv evidence on control/cmd, scenario rupture, load 0.40, RED alerts,
      node statuses) — the arc the presenter narrates.
  3. The t=75 'rupture' cmd reaches a REAL ``DamageInjector`` through a live
     Simulator's ``control/cmd`` subscription, arms the tendon-snap impact
     pulse, and ramps alpha 0 -> 1 per the seeded physics.
  4. A ramp regression: 'healthy' ramps alpha back to 0, and the impact pulse
     measurably energizes the stream (impact-window RMS >> healthy baseline).

The cv beat's real YOLO inference is stubbed to a deterministic evidence dict so
this test stays fast; the REAL cv evidence path (frame -> crack_seg.pt -> cv) is
pinned by smoke_test's demo section + test_cv_feed.

Run:  python backend/tests/test_demo_driver.py
"""
from __future__ import annotations

import logging
import re
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402

from app import events  # noqa: E402
from app.config import Settings  # noqa: E402
from app.demo_driver import BEATS, DemoDriver  # noqa: E402
from app.mqtt_client import Publisher  # noqa: E402

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


# Deterministic stand-in for cv_feed.evidence (real inference pinned elsewhere).
_FAKE_EVIDENCE = {"cv": 0.312, "conf": 0.625, "area_norm": 0.0172,
                  "model": "crack_seg.pt", "source": "cv_feed", "fallback": False}


def _stub_cv_evidence(frame: str, fallback: float) -> dict:
    return dict(_FAKE_EVIDENCE, frame=frame)


def _run_timeline(driver: DemoDriver) -> list[str]:
    """Run driver.run() in a thread; return the 7 beat names in firing order.

    Watches the driver's own INFO log for the beat-firing lines, waits for the
    final 'hold' beat, stops the driver, and returns the deduplicated beat names
    in first-seen order (the cv beat logs an extra 'cv evidence' line carrying
    the same beat name — dedupe drops the duplicate, not the beat).
    """
    logger = logging.getLogger("app.demo_driver")
    logger.setLevel(logging.INFO)
    lines: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda rec: lines.append(rec.getMessage())
    logger.addHandler(handler)
    try:
        t = threading.Thread(target=driver.run, daemon=True)
        t.start()
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if any("beat hold" in ln for ln in lines):
                break
            time.sleep(0.01)
        driver.stop()
        t.join(timeout=5.0)
    finally:
        logger.removeHandler(handler)

    known = set(b["name"] for b in BEATS)
    seen: list[str] = []
    for ln in lines:
        m = re.search(r"beat (\S+)", ln)
        if m and m.group(1) in known and m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def test_beat_sequence() -> None:
    print("[demo-driver] full beat sequence + payloads")
    bus = events.get_bus()
    pub = FakePublisher()
    cfg = Settings()  # ramp_s default 10.0; storyboard time compressed by speed
    driver = DemoDriver(cfg, bus, pub, timeline="demo", speed=200.0)

    cmds: list[dict] = []
    tok = bus.subscribe("control/cmd", lambda t, p: cmds.append(p))

    import app.cv_feed as cvf
    orig = cvf.evidence
    cvf.evidence = _stub_cv_evidence
    try:
        names = _run_timeline(driver)
    finally:
        cvf.evidence = orig
        bus.unsubscribe(tok)

    expected = [b["name"] for b in BEATS]
    check("all 7 beats fired in storyboard order", names == expected,
          f"got {names}")
    check("exactly 7 beats (no duplicates)", len(names) == 7, str(len(names)))

    # control/cmd sequence: cv(mild) -> scenario rupture -> load 0.40 -> cv(severe)
    cv_cmds = [c for c in cmds if c.get("cmd") == "cv"]
    check("2 cv evidence cmds (t=45, t=110)", len(cv_cmds) == 2, str(cv_cmds))
    if len(cv_cmds) == 2:
        check("cv cmd order: mild then severe frame",
              cv_cmds[0]["frame"] == "mild_crack.jpg"
              and cv_cmds[1]["frame"] == "severe_crack.jpg")
        check("cv cmd carries real source + evidence fields",
              cv_cmds[0]["source"] == "cv_feed"
              and cv_cmds[0]["conf"] == 0.625
              and cv_cmds[0]["model"] == "crack_seg.pt")
    scen = [c for c in cmds if c.get("cmd") == "scenario"]
    check("rupture scenario cmd fired once (t=75)",
          len(scen) == 1 and scen[0]["scenario"] == "rupture")
    loads = [c for c in cmds if c.get("cmd") == "load"]
    check("load evidence 0.40 fired once (t=110)",
          len(loads) == 1 and abs(float(loads[0]["value"]) - 0.40) < 1e-9)

    # alerts in order: cv warning (real conf/area embedded) -> vib warning ->
    # fusion critical RED -> fusion critical copilot
    sevs = [a.get("severity") for a in pub.alerts]
    srcs = [a.get("source") for a in pub.alerts]
    check("4 alerts in storyboard order",
          len(pub.alerts) == 4 and sevs == ["warning", "warning", "critical", "critical"],
          f"sevs={sevs}")
    check("alert sources: cv, vib, fusion, fusion", srcs == ["cv", "vib", "fusion", "fusion"],
          f"srcs={srcs}")
    if pub.alerts and pub.alerts[0]["source"] == "cv":
        text = pub.alerts[0]["text"]
        check("cv alert embeds REAL conf + area (not scripted)",
              "conf 0.62" in text and "1.7%" in text, repr(text))
    check("RED alert names the BHI drop",
          any("Bridge Health Index dropped to RED" in a["text"] for a in pub.alerts))

    # statuses: 3 heartbeats at t=20 + 1 firmware update at t=140
    check("4 status events (3 t=20 + 1 t=140)", len(pub.status) == 4, str(len(pub.status)))
    if len(pub.status) >= 4:
        check("t=20 heartbeats for nodes 6,7,8",
              [s.get("node") for s in pub.status[:3]] == [6, 7, 8])
        check("t=140 status carries firmware",
              pub.status[3].get("firmware") == "vitish-edge-0.1"
              and pub.status[3].get("node") == 7)


def test_rupture_reaches_injector() -> None:
    print("[demo-driver] t=75 rupture reaches DamageInjector + ramp/impact")
    bus = events.get_bus()
    pub = FakePublisher()
    cfg = Settings(ramp_s=0.4, impact_s=0.4)  # short ramp for the regression

    from app import simulator as sim_mod
    sim = sim_mod.Simulator(cfg, pub, bus=bus, synthetic=True)
    inj = sim.injector
    check("injector starts healthy (alpha 0)",
          inj.scenario == "healthy" and abs(inj._alpha_now()) < 1e-9)

    driver = DemoDriver(cfg, bus, pub, timeline="demo", speed=200.0)
    import app.cv_feed as cvf
    orig = cvf.evidence
    cvf.evidence = _stub_cv_evidence
    try:
        names = _run_timeline(driver)
    finally:
        cvf.evidence = orig

    check("driver completed all 7 beats", len(names) == 7, str(names))
    # the driver's t=75 scenario cmd must have reached the injector through the
    # Simulator's control/cmd subscription (the real wiring, not a direct call).
    check("t=75 rupture reaches DamageInjector", inj.scenario == "rupture",
          inj.scenario)
    check("tendon-snap impact pulse armed on onset", inj.impact_t0 is not None)

    # ramp regression: alpha slides to 1.0 over ramp_s, then healthy slides back
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if abs(inj._alpha_now() - 1.0) < 1e-6:
            break
        time.sleep(0.02)
    check("rupture alpha ramps to 1.0 (seeded physics, not a step)",
          abs(inj._alpha_now() - 1.0) < 1e-6, f"{inj._alpha_now():.3f}")

    bus.publish("control/cmd", {"cmd": "scenario", "scenario": "healthy"})
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if abs(inj._alpha_now()) < 1e-6:
            break
        time.sleep(0.02)
    check("healthy ramps alpha back to 0", abs(inj._alpha_now()) < 1e-6,
          f"{inj._alpha_now():.3f}")

    # impact regression: within impact_s of onset the stream is measurably
    # energized (broadband 'tendon snap' burst), far above the healthy floor.
    inj.set_scenario("rupture")           # fresh onset -> fresh impact_t0
    win = inj.current_window(6)            # sample inside the impact window
    hw = inj.healthy.current_window(6)
    impact_rms = float(np.sqrt(np.mean(win ** 2)))
    healthy_rms = float(np.sqrt(np.mean(hw ** 2)))
    check("tendon-snap impact energizes the stream (RMS >> healthy)",
          impact_rms > 3.0 * max(healthy_rms, 1e-9),
          f"{impact_rms:.3f} vs {healthy_rms:.3f}")

    bus.unsubscribe(sim._control_token)


def main() -> int:
    try:
        test_beat_sequence()
        test_rupture_reaches_injector()
    except Exception as exc:  # pragma: no cover
        global FAIL
        FAIL += 1
        FAILURES.append("demo-driver tests")
        import traceback
        print(f"  [ERROR] demo-driver tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== demo-driver gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
