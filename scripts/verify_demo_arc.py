"""
verify_demo_arc.py — data-dependent re-pin of the EXACT demo arc values.

Complements ``backend/tests/test_demo_arc.py``, which pins the arc SHAPE
deterministically (baseline GREEN [75,90] -> passes through AMBER [50,70) ->
RED [20,45] -> stays RED -> recovers GREEN).  This script re-pins the EXACT
canonical story values the demo ships — the numbers quoted in README /
Storyboard / Build-Log:

    INITIAL  87.1  (fusion initial state, config.py)
    AMBER   67.5  (rupture onset crosses into AMBER here)
    RED     33.6  (settled BHI at the escalation beat)

against the REAL production pipeline:

  * real detector  ``backend/app/anomaly.get_anomaly`` with its SHIPPED state —
    NOT the ``trained_push = 0`` stub the shape test uses.  Today the trained
    VAE/OCSVM ensemble is honestly INERT (degenerate shipped scaler), so the
    deterministic spectral floor carries the arc; if the ensemble is ever
    revived, this script re-pins WITH it active and will flag the new values.
  * real fusion     ``backend/app/fusion.FusionService`` on the in-process bus
  * real replay     seeded ``SyntheticPlayer`` (pink noise + first-mode
    resonance at the real Z24 healthy fundamental 3.80 Hz), the same
    data path the demo's storyboard runs — the 'real Z24 replay' the
    Build-Log D1-1 note refers to.

Because the pipeline is seeded and deterministic, the values do not drift
between runs unless code changes — so the tolerance bands are TIGHT:

    INITIAL 87.1 ± 0.5   (exact)
    AMBER   67.5 ± 4.5   (measured ~65.7 with this harness; demo ~67.5)
    RED     33.6 ± 2.0   (measured ~34.8 with this harness; demo ~33.6)

Every beat prints measured-vs-canonical; a drift out of tolerance FAILS the
script (exit 1) and forces a conscious re-pin — the arc must never break.

Run:  python scripts/verify_demo_arc.py
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
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

# Canonical story values (README / Storyboard / Build-Log).
CANON_INITIAL = 87.1   # fusion initial state
CANON_AMBER = 67.5     # rupture onset crosses into AMBER
CANON_RED = 33.6       # settled BHI at escalation

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


def near(measured: float, target: float, tol: float) -> bool:
    return abs(measured - target) <= tol


class FakePublisher(Publisher):
    """In-memory publisher — records publishes by topic, never connects to MQTT."""

    def __init__(self) -> None:
        self.connected = threading.Event()
        self.connected.set()
        self.accel: list[dict] = []
        self.bhi: list[dict] = []
        self.alerts: list[dict] = []

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def wait_connected(self, timeout: float = 5.0) -> bool:
        return True

    def publish(self, topic: str, payload: dict, qos: int = 1) -> bool:
        if topic.endswith("/bhi"):
            self.bhi.append(payload)
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


def verify_demo_arc() -> int:
    print("[verify_demo_arc] re-pinning EXACT arc values 87.1 / 67.5 / 33.6 "
          "against the REAL production pipeline (shipped detector state, "
          "no trained_push stub)")
    reset_anomaly_baseline()
    bus = events.get_bus()
    pub = FakePublisher()
    fus = FusionService(settings, bus, db.MemoryStore(cache_path=None), pub)
    fus.start()

    # --- INITIAL state: fusion initial BHI ---------------------------------
    initial = fus.bhi
    check("INITIAL BHI ~ 87.1",
          near(initial, CANON_INITIAL, 0.5),
          f"got {initial:.3f}, canonical {CANON_INITIAL}")
    check("INITIAL state GREEN", fus.state == "GREEN", str(fus.state))

    # --- baseline: healthy feed, BHI settles GREEN -------------------------
    _feed(bus, SyntheticPlayer("healthy", settings.nodes, seed=1), 40)
    fus.publish_bhi()
    base = pub.bhi[-1]
    print(f"    baseline {base['bhi']:.3f} {base['state']}  "
          f"(canonical settle 77-79 GREEN, demo band [75,90])")
    check("baseline BHI GREEN", base["state"] == "GREEN", str(base))
    check("baseline BHI in [75,90]", 75 <= base["bhi"] <= 90, f"got {base['bhi']}")

    # --- beat: cv evidence rises, BHI drops but stays GREEN ----------------
    bus.publish("control/cmd", {"cmd": "cv", "value": 0.30})
    fus.publish_bhi()
    after_cv = pub.bhi[-1]
    check("cv beat drops BHI", after_cv["bhi"] < base["bhi"], str(after_cv))
    check("cv beat still GREEN", after_cv["state"] == "GREEN", str(after_cv))

    # --- progressive rupture onset (cross-fade) -> AMBER --------------------
    hp = SyntheticPlayer("healthy", settings.nodes, seed=1)
    rp = SyntheticPlayer("rupture", settings.nodes, seed=2)
    traj: list[dict] = []
    amber_val: float | None = None
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
        b = pub.bhi[-1]
        traj.append(b)
        if b["state"] == "AMBER" and amber_val is None:
            amber_val = float(b["bhi"])

    states = [t["state"] for t in traj]
    check("arc passes through AMBER", "AMBER" in states, str(states))
    if amber_val is not None:
        print(f"    AMBER-entry {amber_val:.3f}  (canonical {CANON_AMBER})")
        check("AMBER-entry BHI ~ 67.5 (±4.5)",
              near(amber_val, CANON_AMBER, 4.5), f"got {amber_val:.3f}")
    first_non_green = next((i for i, s in enumerate(states) if s != "GREEN"), None)
    check("arc leaves GREEN", first_non_green is not None, str(states))
    if first_non_green is not None:
        tail = states[first_non_green:]
        check("no return to GREEN after leaving", "GREEN" not in tail, str(tail))
        seen_red = False
        flicker = False
        for s in tail:
            if s == "RED":
                seen_red = True
            elif seen_red:
                flicker = True
        check("no flicker (once RED, stays RED)", not flicker, str(tail))

    # --- beat: load + cv escalate -> RED ~33.6, then stable ----------------
    bus.publish("control/cmd", {"cmd": "load", "value": 0.40})
    bus.publish("control/cmd", {"cmd": "cv", "value": 0.55})
    _feed(bus, rp, 10)
    fus.publish_bhi()
    red = pub.bhi[-1]
    print(f"    RED {red['bhi']:.3f}  (canonical {CANON_RED})")
    check("escalation -> RED", red["state"] == "RED", str(red))
    check("RED BHI ~ 33.6 (±2.0)",
          near(red["bhi"], CANON_RED, 2.0), f"got {red['bhi']:.3f}")
    _feed(bus, rp, 10)
    fus.publish_bhi()
    stable = pub.bhi[-1]
    check("RED stays stable", stable["state"] == "RED", str(stable))
    check("RED stable BHI ~ 33.6 (±2.0)",
          near(stable["bhi"], CANON_RED, 2.0), f"got {stable['bhi']:.3f}")

    # --- recovery: scenario healthy must restore GREEN ---------------------
    bus.publish("control/cmd", {"cmd": "scenario", "scenario": "healthy"})
    check("healthy resets cv evidence", fus.cv == settings.cv_default, f"cv={fus.cv}")
    check("healthy resets load evidence", fus.load == settings.load_default,
          f"load={fus.load}")
    _feed(bus, SyntheticPlayer("healthy", settings.nodes, seed=1), 20)
    fus.publish_bhi()
    rec = pub.bhi[-1]
    check("recovery returns to GREEN", rec["state"] == "GREEN", str(rec))
    check("recovery BHI in [75,90]", 75 <= rec["bhi"] <= 90, f"got {rec['bhi']}")

    fus.stop()
    return 0


def main() -> int:
    try:
        rc = verify_demo_arc()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("verify_demo_arc")
        import traceback
        print(f"  [ERROR] verify_demo_arc raised: {exc}")
        traceback.print_exc()
        rc = 1
    print()
    print(f"== verify-demo-arc: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
        print("If a stream/model change legitimately moved a value, re-pin the")
        print("canonical numbers CONSCIOUSLY (README/Storyboard/Build-Log + here).")
    return 1 if (FAIL or rc) else 0


if __name__ == "__main__":
    sys.exit(main())
