"""
VITISH 2026 · PS#99 SHM — BHI fusion service.

Consumes ``bridge/z24/accel`` events from the shared event bus, runs the
anomaly interface (:func:`app.anomaly.get_anomaly`) on a sliding 10.24 s
window per node, and fuses the three sub-indices into the auditable Bridge
Health Index defined in the contract::

    BHI = 100 * (1 - 0.40*cv - 0.35*vib - 0.25*load)   state: GREEN>=70,
                                                       AMBER [50,70), RED<50

``vib`` is driven by the live signal (spectral heuristic / real model).
``cv`` and ``load`` are evidence sub-indices; in the demo they are set through
``control/cmd`` events (the CV branch feeds ``cv`` from crack detections; load
comes from the simulated traffic envelope).  Defaults yield a healthy baseline
of ~87 (GREEN) and the demo story drops it through AMBER into RED.

BHI snapshots are emitted with :func:`app.mqtt_client.emit` — to MQTT when the
broker is up, otherwise directly on the event bus — so the persistence recorder
and the WebSocket bridge see each snapshot exactly once.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

import numpy as np

from app import contract
from app.anomaly import get_anomaly
from app.config import Settings
from app.mqtt_client import Publisher, emit

log = logging.getLogger(__name__)


class FusionService:
    def __init__(self, cfg: Settings, bus, store, publisher: Publisher) -> None:
        self.cfg = cfg
        self.bus = bus
        self.store = store
        self.publisher = publisher

        self.cv = cfg.cv_default
        self.load = cfg.load_default
        self.vib = cfg.vib_base
        self.u = 0.05
        self.state = "GREEN"
        self.bhi = contract.compute_bhi(self.cv, self.vib, self.load)
        self.last_ts: Optional[float] = None

        self._rings: Dict[int, Deque[float]] = {
            node: deque(maxlen=cfg.window_n) for node in cfg.nodes
        }
        self._node_scores: Dict[int, float] = {}
        self._lock = threading.RLock()
        self._last_pub = 0.0
        self._first = True
        self._accel_token: Optional[int] = None
        self._control_token: Optional[int] = None

    # -- lifecycle ---------------------------------------------------------------
    def start(self) -> None:
        self._accel_token = self.bus.subscribe(
            f"bridge/{self.cfg.bridge_id}/accel", self.on_accel)
        self._control_token = self.bus.subscribe("control/cmd", self.on_control)
        log.info("fusion service running (vib baseline %.2f, cv %.2f, load %.2f)",
                 self.vib, self.cv, self.load)

    def stop(self) -> None:
        if self._accel_token is not None:
            self.bus.unsubscribe(self._accel_token)
        if self._control_token is not None:
            self.bus.unsubscribe(self._control_token)

    # -- control ------------------------------------------------------------------
    def on_control(self, topic: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        cmd = payload.get("cmd")
        if cmd == "cv" and "value" in payload:
            self.cv = float(max(0.0, min(1.0, payload["value"])))
            log.info("fusion: cv evidence -> %.2f", self.cv)
        elif cmd == "load" and "value" in payload:
            self.load = float(max(0.0, min(1.0, payload["value"])))
            log.info("fusion: load index -> %.2f", self.load)
        elif cmd == "scenario" and payload.get("scenario") == "healthy":
            # Recovery from a held alert state: the simulator relaxes vib on its
            # own (healthy ramps the damage injector out), but cv/load are held
            # by fusion — restore their baselines here so the bridge returns to
            # GREEN instead of stalling at AMBER with stale evidence.
            self.cv = self.cfg.cv_default
            self.load = self.cfg.load_default
            log.info("fusion: scenario healthy -> cv %.2f, load %.2f (baseline reset)",
                     self.cv, self.load)

    # -- accel path ----------------------------------------------------------------
    def on_accel(self, topic: str, payload: Any) -> None:
        if not isinstance(payload, dict) or not payload.get("samples"):
            return
        node = payload.get("node")
        with self._lock:
            ring = self._rings.setdefault(
                int(node), deque(maxlen=self.cfg.window_n))
            ring.extend(payload["samples"])
            if len(ring) >= self.cfg.window_n:
                score, unc = get_anomaly(list(ring))
                self._node_scores[int(node)] = score
                target = self.cfg.vib_base + score * (1.0 - self.cfg.vib_base)
                self.vib = 0.6 * self.vib + 0.4 * target
                scores = list(self._node_scores.values())
                spread = float(np.std(scores)) if scores else 0.0
                self.u = round(min(0.40, 0.03 + 0.30 * self.vib + 0.40 * spread), 3)

            now = time.monotonic()
            candidate = contract.state_for(contract.compute_bhi(self.cv, self.vib, self.load))
            should_pub = self._first or (now - self._last_pub >= self.cfg.bhi_publish_interval)
            if not should_pub and candidate != self.state and (now - self._last_pub >= 0.5):
                should_pub = True  # snap the BHI gauge on a band crossing
            if should_pub:
                self._first = False
                self._last_pub = now
                self.publish_bhi()

    def publish_bhi(self) -> None:
        self.bhi = contract.compute_bhi(self.cv, self.vib, self.load)
        self.state = contract.state_for(self.bhi)
        self.last_ts = contract.now()
        payload = {
            "bridge": self.cfg.bridge_id,
            "ts": self.last_ts,
            "bhi": self.bhi,
            "u": self.u,
            "cv": round(self.cv, 3),
            "vib": round(self.vib, 3),
            "load": round(self.load, 3),
            "state": self.state,
            "msg_id": f"fus-{int(time.monotonic() * 1000)}",
        }
        topic = contract.TOPIC_BHI.format(bridge=self.cfg.bridge_id)
        emit(topic, payload, self.publisher, bus=self.bus,
             qos=contract.QOS_TELEMETRY)
        log.debug("BHI=%.1f state=%s cv=%.2f vib=%.2f load=%.2f u=%.3f",
                  self.bhi, self.state, self.cv, self.vib, self.load, self.u)
