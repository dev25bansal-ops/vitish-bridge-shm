"""
VITISH 2026 · PS#99 SHM — 6-minute storyboard demo driver.

Advances the demo deterministically through a fixed timeline of beats, each of
which may (a) inject damage, (b) publish a canned alert, or (c) emit a status
change.  It is the *storyboard controller*, not the data path — the simulator,
fusion service and pipeline run regardless; the driver only nudges evidence and
publishes the narrative beats on schedule.

Story arc (times relative to driver start, scale with --speed):

    t=0     healthy baseline, BHI ~87, GREEN
    t=20    node heartbeat / monitoring active
    t=45    CRACK DETECTED (CV) -> cv evidence up, warning alert
    t=75    VIBRATION ANOMALY -> rupture onset, anomaly score rises
    t=110   BHI DROPS 87 -> RED (load evidence up + critical alert)
    t=140   COPILOT RECOMMENDATION (tendon-rupture signature)
    t=175   hold alert state

CLI:  python app/demo_driver.py [--timeline demo] [--speed 1.0] [--json]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# launch bootstrap (works from repo root or backend/)
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import contract  # noqa: E402
from app.config import Settings, settings  # noqa: E402
from app.events import EventBus, get_bus  # noqa: E402
from app.mqtt_client import Publisher, emit  # noqa: E402

log = logging.getLogger(__name__)

# beat: {"t": seconds, "name": str, "desc": str, "actions": [dict ...]}
#   action kinds: {"kind": "cmd", "payload": {...}}          -> control/cmd
#                 {"kind": "alert", "payload": {...}}         -> bridge/<id>/alert
#                 {"kind": "status", "payload": {...}}        -> bridge/<id>/status
BEATS: List[Dict[str, Any]] = [
    {
        "t": 0.0, "name": "healthy-baseline", "desc": "Healthy baseline — BHI ~87, GREEN, all nodes streaming at 100 Hz",
        "actions": [],
    },
    {
        "t": 20.0, "name": "monitoring-status", "desc": "Node heartbeats online · 100 Hz streaming",
        "actions": [
            {"kind": "status", "payload": {"node": 6, "online": True, "rssi": -63}},
            {"kind": "status", "payload": {"node": 7, "online": True, "rssi": -61}},
            {"kind": "status", "payload": {"node": 8, "online": True, "rssi": -66}},
        ],
    },
    {
        "t": 45.0, "name": "crack-detected", "desc": "CV model detects crack at section 3 — visual evidence rises",
        "actions": [
            {"kind": "cmd", "payload": {"cmd": "cv", "value": 0.30}},
            {"kind": "alert", "payload": {
                "severity": "warning", "source": "cv",
                "text": "Crack detected at section 3 (web) — 12.4 cm, conf 0.87",
                "recommendation": "Schedule close visual inspection; correlate with vibration"}},
        ],
    },
    {
        "t": 75.0, "name": "vibration-anomaly", "desc": "Tendon-rupture signature onset — vibration anomaly score rises",
        "actions": [
            {"kind": "cmd", "payload": {"cmd": "scenario", "scenario": "rupture"}},
            {"kind": "alert", "payload": {
                "severity": "warning", "source": "vib",
                "text": "Vibration anomaly score crossing threshold (4 Hz modal band)",
                "recommendation": "Correlate with CV and load evidence"}},
        ],
    },
    {
        "t": 110.0, "name": "bhi-drop", "desc": "BHI drops 87 → RED (load + CV evidence push it critical)",
        "actions": [
            {"kind": "cmd", "payload": {"cmd": "load", "value": 0.40}},
            {"kind": "cmd", "payload": {"cmd": "cv", "value": 0.55}},
            {"kind": "alert", "payload": {
                "severity": "critical", "source": "fusion",
                "text": "Bridge Health Index dropped to RED (crossed 50 — critical)",
                "recommendation": "Restrict traffic; dispatch inspection crew"}},
        ],
    },
    {
        "t": 140.0, "name": "copilot-recommendation", "desc": "LLM copilot recommendation — tendon-rupture signature confirmed",
        "actions": [
            {"kind": "status", "payload": {"node": 7, "online": True, "rssi": -62,
                                           "firmware": "vitish-edge-0.1"}},
            {"kind": "alert", "payload": {
                "severity": "critical", "source": "fusion",
                "text": "Tendon-rupture signature detected — recommend load restriction and strain-gauge verification",
                "recommendation": "Load restrict to < 7.5 t; deploy strain gauges on tendon bundle; re-check in 24 h"}},
        ],
    },
    {
        "t": 175.0, "name": "hold", "desc": "Hold alert state for inspection flow",
        "actions": [],
    },
]

TIMELINES = {"demo": BEATS}


def _alert_payload(cfg: Settings, a: dict, i: int) -> dict:
    return {
        "bridge": cfg.bridge_id,
        "ts": contract.now(),
        "severity": a["severity"],
        "source": a["source"],
        "text": a["text"],
        "recommendation": a.get("recommendation", ""),
        "msg_id": f"drv-{int(time.monotonic() * 1000)}-{i}",
    }


def _status_payload(cfg: Settings, a: dict, i: int) -> dict:
    return {
        "bridge": cfg.bridge_id,
        "node": a.get("node", cfg.nodes[0]),
        "ts": contract.now(),
        "online": bool(a.get("online", True)),
        "firmware": a.get("firmware", "vitish-edge-0.1"),
        "rssi": int(a.get("rssi", -62)),
        "msg_id": f"drv-{int(time.monotonic() * 1000)}-{i}",
    }


class DemoDriver:
    def __init__(self, cfg: Settings, bus: EventBus, publisher: Publisher,
                 timeline: str = "demo", speed: float = 1.0) -> None:
        self.cfg = cfg
        self.bus = bus
        self.publisher = publisher
        self.speed = max(float(speed), 0.05)
        self.beats = TIMELINES.get(timeline, BEATS)
        self._stop = threading.Event()

    # -- execution -----------------------------------------------------------------
    def run(self) -> None:
        log.info("demo driver starting: %d beats over ~%.0fs at speed %.2fx",
                 len(self.beats), self.beats[-1]["t"] / self.speed, self.speed)
        t0 = time.monotonic()
        for i, beat in enumerate(self.beats):
            wait = beat["t"] / self.speed - (time.monotonic() - t0)
            if wait > 0 and self._stop.wait(wait):
                break
            if self._stop.is_set():
                break
            self._fire(beat, i)
            elapsed = time.monotonic() - t0
            log.info("[%5.1fs] beat %-24s %s", elapsed, beat["name"], beat["desc"])
        log.info("demo driver: timeline complete — holding final state")
        self._stop.wait()

    def _fire(self, beat: dict, idx: int) -> None:
        for j, action in enumerate(beat.get("actions", [])):
            kind = action.get("kind")
            payload = action.get("payload", {})
            if kind == "cmd":
                self.bus.publish("control/cmd", dict(payload, source="demo_driver"),
                                 source="demo_driver")
            elif kind == "alert":
                emit(contract.TOPIC_ALERT.format(bridge=self.cfg.bridge_id),
                     _alert_payload(self.cfg, payload, idx * 10 + j),
                     self.publisher, bus=self.bus)
            elif kind == "status":
                emit(contract.TOPIC_STATUS.format(bridge=self.cfg.bridge_id),
                     _status_payload(self.cfg, payload, idx * 10 + j),
                     self.publisher, bus=self.bus)

    def stop(self) -> None:
        self._stop.set()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="VITISH SHM storyboard demo driver")
    parser.add_argument("--timeline", choices=list(TIMELINES), default="demo")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="playback speed multiplier (1.0 = storyboard time)")
    parser.add_argument("--json", action="store_true",
                        help="print the beat list as JSON and exit")
    args = parser.parse_args(argv)

    if args.json:
        print(json.dumps(TIMELINES[args.timeline], indent=2))
        return 0

    logging.basicConfig(level=logging.INFO)
    cfg = settings
    bus = get_bus()
    publisher = Publisher(cfg)
    publisher.start()
    driver = DemoDriver(cfg, bus, publisher, timeline=args.timeline, speed=args.speed)
    try:
        driver.run()
    except KeyboardInterrupt:
        print("\ndemo driver stopped (Ctrl-C)")
    finally:
        driver.stop()
        publisher.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
