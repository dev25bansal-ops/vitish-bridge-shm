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

from app import bridge_registry, contract
from app.anomaly import get_anomaly, last_evidence
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
        # ROADMAP line 68: floor vs trained-push split of the last scored window,
        # surfaced in the BHI message so the UI credits whichever detector is
        # actually carrying the arc.
        self.vib_evidence = {"floor": 0.0, "trained_push": 0.0, "score": 0.0}
        self.u = contract.uncertainty_points(0.05)  # ±BHI points (initial ~0.5)
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

        # item 14 (bridge registry): per-extra-bridge fusion state, heuristic
        # vib path ONLY.  Extras must NEVER call get_anomaly(): the anomaly
        # baseline + the module-global last_evidence() belong exclusively to the
        # hero path (see _hero_accel) — a second caller would clobber the hero's
        # evidence window.  Extra BHI is driven by a RMS-deviation heuristic
        # against the extra's OWN rolling baseline, so a stable synthetic channel
        # hovers at its healthy baseline without ever borrowing model evidence.
        self._extra_ids = set(bridge_registry.extra_bridge_ids())
        self._extras: Dict[str, dict] = {}
        for _bid in self._extra_ids:
            self._extras[_bid] = {
                "cv": cfg.cv_default,
                "load": cfg.load_default,
                "vib": cfg.vib_base,
                "u": contract.uncertainty_points(0.05),
                "rms_ema": {},
                "last_pub": 0.0,
                "first": True,
            }

    # -- lifecycle ---------------------------------------------------------------
    def start(self) -> None:
        # item 14: bridge/+/accel covers the hero AND every env-registered extra
        # bridge; on_accel routes by the topic's id (see on_accel).
        self._accel_token = self.bus.subscribe("bridge/+/accel", self.on_accel)
        self._control_token = self.bus.subscribe("control/cmd", self.on_control)
        log.info("fusion service running (vib baseline %.2f, cv %.2f, load %.2f; "
                 "extra bridges: %s)",
                 self.vib, self.cv, self.load,
                 ",".join(sorted(self._extra_ids)) or "none")

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
            # GREEN instead of stalling at AMBER with stale evidence.  Extra
            # bridges (item 14) reset the same way — they share the demo story.
            self.cv = self.cfg.cv_default
            self.load = self.cfg.load_default
            for st in self._extras.values():
                st["cv"] = self.cfg.cv_default
                st["load"] = self.cfg.load_default
                st["vib"] = self.cfg.vib_base
            log.info("fusion: scenario healthy -> cv %.2f, load %.2f (baseline reset)",
                     self.cv, self.load)

    # -- accel path ----------------------------------------------------------------
    def on_accel(self, topic: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        samples = payload.get("samples")
        # item 11 (ROADMAP-NEXT): a truthy non-numeric payload (e.g. a string)
        # would extend the ring with garbage — require an actual list of numbers.
        if not isinstance(samples, (list, tuple)) or len(samples) == 0:
            return
        parts = topic.split("/")
        bridge = parts[1] if len(parts) > 1 and parts[0] == "bridge" else self.cfg.bridge_id
        node = payload.get("node")
        with self._lock:
            if bridge == self.cfg.bridge_id:
                # hero path — byte-for-byte the item-1 logic (moved to a helper)
                self._hero_accel(node, samples)
            elif bridge in self._extra_ids:
                # item 14: registered extra bridge — heuristic-only path
                self._extra_accel(bridge, node, samples)
            # else: a non-registry bridge (edge nodes, live-demo).  Fusion never
            # fuses those feeds into a BHI — they have their own handlers.

    def _hero_accel(self, node: Any, samples) -> None:
        """The hero bridge's anomaly-scored BHI path (unchanged from item 1)."""
        ring = self._rings.setdefault(
            int(node), deque(maxlen=self.cfg.window_n))
        ring.extend(float(x) for x in samples)
        if len(ring) >= self.cfg.window_n:
            score, unc = get_anomaly(list(ring))
            self.vib_evidence = last_evidence()  # ROADMAP line 68
            self._node_scores[int(node)] = score
            target = self.cfg.vib_base + score * (1.0 - self.cfg.vib_base)
            self.vib = 0.6 * self.vib + 0.4 * target
            scores = list(self._node_scores.values())
            spread = float(np.std(scores)) if scores else 0.0
            # normalized [0, 0.4] evidence uncertainty -> ±BHI points at
            # publish (ROADMAP line 45: u semantic is points, not fraction)
            self.u = contract.uncertainty_points(
                round(min(0.40, 0.03 + 0.30 * self.vib + 0.40 * spread), 3))

        now = time.monotonic()
        candidate = contract.state_for(contract.compute_bhi(self.cv, self.vib, self.load))
        should_pub = self._first or (now - self._last_pub >= self.cfg.bhi_publish_interval)
        if not should_pub and candidate != self.state and (now - self._last_pub >= 0.5):
            should_pub = True  # snap the BHI gauge on a band crossing
        if should_pub:
            self._first = False
            self._last_pub = now
            self.publish_bhi()

    def _extra_accel(self, bridge: str, node: Any, samples) -> None:
        """Heuristic-only BHI for a registered extra bridge (item 14).

        No get_anomaly() / last_evidence() here — see the __init__ comment.
        The vib lever is the RELATIVE RMS deviation of the current window against
        the extra's own rolling EMA baseline: a stable synthetic channel sits at
        ``dev = 0`` and the BHI holds its healthy baseline, while a drifting or
        spiking stream would raise it.  Honest: this is a heuristic on a
        synthetic channel, not a trained detector for that bridge.
        """
        st = self._extras.get(bridge)
        if st is None:
            return
        rms = float(np.sqrt(np.mean(np.asarray(samples, dtype=float) ** 2)))
        ema = st["rms_ema"].get(node)
        ema = rms if ema is None else 0.9 * ema + 0.1 * rms
        st["rms_ema"][node] = ema
        dev = max(0.0, rms - ema) / max(ema, 1e-9)
        target = min(1.0, self.cfg.vib_base + 0.30 * dev)
        st["vib"] = 0.6 * st["vib"] + 0.4 * target
        now = time.monotonic()
        if st["first"] or (now - st["last_pub"] >= self.cfg.bhi_publish_interval):
            st["first"] = False
            st["last_pub"] = now
            self._publish_extra_bhi(bridge, st)

    def _publish_extra_bhi(self, bridge: str, st: dict) -> None:
        bhi = contract.compute_bhi(st["cv"], st["vib"], st["load"])
        state = contract.state_for(bhi)
        payload = {
            "bridge": bridge,
            "ts": contract.now(),
            "bhi": bhi,
            "u": st["u"],
            "cv": round(st["cv"], 3),
            "vib": round(st["vib"], 3),
            "load": round(st["load"], 3),
            "state": state,
            "source": "simulated-extra",  # honest: heuristic on a synthetic channel
            "msg_id": f"fus-{bridge}-{int(time.monotonic() * 1000)}",
        }
        topic = contract.TOPIC_BHI.format(bridge=bridge)
        emit(topic, payload, self.publisher, bus=self.bus,
             qos=contract.QOS_TELEMETRY)
        log.debug("extra bridge %s BHI=%.1f state=%s (heuristic)",
                  bridge, bhi, state)

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
            "vib_evidence": dict(self.vib_evidence),  # ROADMAP line 68
            "msg_id": f"fus-{int(time.monotonic() * 1000)}",
        }
        topic = contract.TOPIC_BHI.format(bridge=self.cfg.bridge_id)
        emit(topic, payload, self.publisher, bus=self.bus,
             qos=contract.QOS_TELEMETRY)
        log.debug("BHI=%.1f state=%s cv=%.2f vib=%.2f load=%.2f u=%.3f",
                  self.bhi, self.state, self.cv, self.vib, self.load, self.u)
