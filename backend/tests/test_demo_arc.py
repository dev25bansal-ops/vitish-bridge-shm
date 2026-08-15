"""
Demo-arc regression gate — pins the GREEN -> AMBER -> RED story.

The demo story arc (87 -> 67.5 -> 33.6) was for a long time a *memory artifact*:
67.5 and 33.6 appeared nowhere in the code, so any stream change could silently
break the story.  This file turns it into an acceptance test.

Strategy (two layers, kept honest):
  * THIS test pins the STORY deterministically: baseline GREEN, cv-evidence beat,
    progressive rupture onset that drives BHI DOWN through AMBER [50,70), and a
    load+cv escalation to RED [20,45] (real demo pins ~33.6), that then STAYS RED
    (no flicker).  It uses seeded synthetic windows + the deterministic spectral-
    heuristic floor (the always-on layer — see app/anomaly.get_anomaly docstring),
    so it runs on any clone with zero data and never depends on trained weights.
  * scripts/verify_demo_arc.py (data-dependent) re-pins the exact values
    87 / 67.5 / 33.6 against the real Z24 replay + trained models.

The demo arc must NEVER break (vault: Key-Decisions, Realistic-Digital-Twin §3).

Run:  python backend/tests/test_demo_arc.py
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import contract, db, events  # noqa: E402
from app.anomaly import reset_anomaly_baseline  # noqa: E402
from app.config import settings  # noqa: E402
from app.fusion import FusionService  # noqa: E402
from app.mqtt_client import Publisher  # noqa: E402
from app.simulator import SyntheticPlayer  # noqa: E402

# Pin the deterministic floor: trained weights (if present locally) must not
# change this gate's expectations — the arc is defined on the always-on floor.
# ROADMAP line 58: the patch is scoped INSIDE the test function and restored in
# a finally, so importing this module never mutates the process-global
# demo_predictor.trained_push (pytest-safe / order-independent).
import models.vibration.demo_predictor as _dp  # noqa: E402
_ORIG_TRAINED_PUSH = _dp.trained_push

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
    """In-memory publisher — records publishes by topic, never connects to MQTT."""

    def __init__(self) -> None:
        self.connected = threading.Event()
        self.connected.set()
        self.accel: list[dict] = []
        self.bhi: list[dict] = []
        self.alerts: list[dict] = []
        self.status: list[dict] = []
        self.all_topics: list[tuple] = []

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def wait_connected(self, timeout: float = 5.0) -> bool:
        return True

    def publish(self, topic: str, payload: dict, qos: int = 1) -> bool:
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


def _feed(bus, player, rounds: int, nodes=(6, 7, 8)) -> None:
    for _ in range(rounds):
        for node in nodes:
            w = player.current_window(node)
            bus.publish("bridge/z24/accel", {
                "bridge": "z24", "node": node, "ts": time.time(),
                "samples": [float(x) for x in w], "fs": 100,
            })
        player.tick()


def test_demo_arc() -> None:
    print("[arc] demo story arc — GREEN -> AMBER -> RED, pinned")
    _dp.trained_push = lambda window, fs=100: 0.0  # noqa: E731
    try:
        _test_demo_arc_body()
    finally:
        # ROADMAP line 58: restore the process-global so importing/running this
        # test never leaks the zero-push stub into other modules (pytest-safe /
        # order-independent).
        _dp.trained_push = _ORIG_TRAINED_PUSH


def _test_demo_arc_body() -> None:
    reset_anomaly_baseline()
    bus = events.get_bus()
    pub = FakePublisher()
    fus = FusionService(settings, bus, db.MemoryStore(cache_path=None), pub)
    fus.start()

    def current() -> float:
        return contract.compute_bhi(fus.cv, fus.vib, fus.load)

    # --- baseline: healthy feed, BHI settles GREEN -------------------------
    _feed(bus, SyntheticPlayer("healthy", settings.nodes, seed=1), 40)
    fus.publish_bhi()
    base = pub.bhi[-1]
    check("baseline BHI GREEN", base["state"] == "GREEN", str(base))
    check("baseline BHI in pinned band [75,90]",
          75 <= base["bhi"] <= 90, f"got {base['bhi']}")

    # --- beat: cv evidence rises, BHI drops but stays GREEN ----------------
    bus.publish("control/cmd", {"cmd": "cv", "value": 0.30})
    fus.publish_bhi()
    after_cv = pub.bhi[-1]
    check("cv beat drops BHI", after_cv["bhi"] < base["bhi"], str(after_cv))
    check("cv beat still GREEN", after_cv["state"] == "GREEN", str(after_cv))

    # --- progressive rupture onset (manual cross-fade, mimics injector) ----
    # Drive BHI DOWN and record the sampled trajectory + states.
    hp = SyntheticPlayer("healthy", settings.nodes, seed=1)
    rp = SyntheticPlayer("rupture", settings.nodes, seed=2)
    traj: list[dict] = []
    for i in range(61):
        alpha = i / 60.0
        for node in settings.nodes:
            w = (1 - alpha) * hp.current_window(node) + alpha * rp.current_window(node)
            bus.publish("bridge/z24/accel", {
                "bridge": "z24", "node": node, "ts": time.time(),
                "samples": [float(x) for x in w], "fs": 100,
            })
        rp.tick()
        hp.tick()
        fus.publish_bhi()
        traj.append(pub.bhi[-1])

    states = [t["state"] for t in traj]
    check("arc passes through AMBER", "AMBER" in states, str(states))
    # leaves GREEN and never returns to it (arc is one-way downhill)
    first_non_green = next((i for i, s in enumerate(states) if s != "GREEN"), None)
    check("arc leaves GREEN", first_non_green is not None, str(states))
    if first_non_green is not None:
        tail = states[first_non_green:]
        check("no return to GREEN after leaving", "GREEN" not in tail, str(tail))
        # no flicker: once RED, never back to AMBER/GREEN
        seen_red = False
        flicker = False
        for s in tail:
            if s == "RED":
                seen_red = True
            elif seen_red:
                flicker = True
        check("no flicker (once RED, stays RED)", not flicker, str(tail))

    # --- beat: load + cv escalate -> RED [20,45], then stable ---------------
    bus.publish("control/cmd", {"cmd": "load", "value": 0.40})
    bus.publish("control/cmd", {"cmd": "cv", "value": 0.55})
    _feed(bus, rp, 10)
    fus.publish_bhi()
    red = pub.bhi[-1]
    check("escalation -> RED", red["state"] == "RED", str(red))
    check("RED BHI in pinned band [20,45] (real demo ~33.6)",
          20 <= red["bhi"] <= 45, f"got {red['bhi']}")
    _feed(bus, rp, 10)
    fus.publish_bhi()
    stable = pub.bhi[-1]
    check("RED stays stable", stable["state"] == "RED", str(stable))

    # --- recovery: scenario healthy must restore GREEN (not stall at AMBER) --
    # The simulator relaxes vib on its own; fusion must ALSO reset the cv/load
    # evidence it holds, or the bridge stalls at AMBER with stale RED evidence.
    bus.publish("control/cmd", {"cmd": "scenario", "scenario": "healthy"})
    check("healthy resets cv evidence", fus.cv == settings.cv_default,
          f"cv={fus.cv}")
    check("healthy resets load evidence", fus.load == settings.load_default,
          f"load={fus.load}")
    _feed(bus, SyntheticPlayer("healthy", settings.nodes, seed=1), 20)
    fus.publish_bhi()
    rec = pub.bhi[-1]
    check("recovery returns to GREEN", rec["state"] == "GREEN", str(rec))
    check("recovery BHI in pinned band [75,90]",
          75 <= rec["bhi"] <= 90, f"got {rec['bhi']}")

    fus.stop()


def main() -> int:
    try:
        test_demo_arc()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("test_demo_arc")
        import traceback
        print(f"  [ERROR] test_demo_arc raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== demo-arc gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
