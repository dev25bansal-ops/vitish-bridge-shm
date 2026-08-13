"""
VITISH 2026 · PS#99 SHM — paho-mqtt helpers.

* :class:`Publisher`   — connects to the broker (with reconnect/backoff), then
  publishes accel / bhi / alert / status payloads in the contract shapes.
* :class:`Subscriber`  — subscribes to bridge topics and dispatches JSON payloads
  to handlers (exact-topic or wildcard default handler).
* :func:`emit`         — the standard producer helper: publish to MQTT, and when
  the broker is unreachable ALSO publish directly on the event bus so the demo
  keeps running without Docker (the subscriber is silent in that case, so there
  is never a duplicate).
* :func:`make_mqtt_router` — bridges MQTT -> event bus for the whole stack.
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

from app import contract
from app.config import Settings

log = logging.getLogger(__name__)


def _json_default(o: Any) -> Any:
    if hasattr(o, "item"):  # numpy scalars
        return o.item()
    if isinstance(o, (list, tuple)):
        return list(o)
    return str(o)


def _as_samples(samples) -> list:
    return [round(float(x), 6) for x in samples]


def _msg_id(prefix: str) -> str:
    return f"{prefix}-{int(time.monotonic() * 1000):d}-{random.randrange(1000, 9999)}"


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------
class Publisher:
    """A single MQTT publisher shared by the whole backend stack."""

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.connected = threading.Event()
        self.published = 0
        self._stop = threading.Event()
        cid = f"vitish-pub-{os.getpid()}-{random.randrange(1000, 9999)}"
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=cid
        )
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.on_connect = self._on_connect
        self._thread: Optional[threading.Thread] = None

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        # paho 2.1.0: reason_code is a ReasonCode — use .value (int() raises TypeError)
        if getattr(reason_code, "value", -1) == 0:
            log.info(
                "MQTT publisher connected to %s:%s",
                self.cfg.broker_host,
                self.cfg.broker_port,
            )
            self.connected.set()
        else:
            log.warning("MQTT publisher connect refused: %s", reason_code)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._connect_loop, name="mqtt-publisher", daemon=True
        )
        self._thread.start()

    def _connect_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.client.connect(
                    self.cfg.broker_host,
                    self.cfg.broker_port,
                    keepalive=self.cfg.mqtt_keepalive,
                )
                self.client.loop_forever()  # blocks; returns on disconnect
            except Exception as exc:
                log.debug("publisher connect failed: %s", exc)
            self.connected.clear()
            if self._stop.is_set():
                break
            time.sleep(2.0)

    def publish(self, topic: str, payload: dict, qos: int = contract.QOS_TELEMETRY) -> bool:
        try:
            info = self.client.publish(topic, json.dumps(payload, default=_json_default), qos=qos)
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                self.published += 1
                return True
            return False
        except Exception:
            return False

    def wait_connected(self, timeout: float = 5.0) -> bool:
        return self.connected.wait(timeout)

    def stop(self) -> None:
        self._stop.set()
        try:
            self.client.disconnect()
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    # -- contract-typed helpers -------------------------------------------------
    def publish_accel(self, node: int, samples, ts: float, rms: float, flag: int,
                      bridge: Optional[str] = None) -> bool:
        bridge = bridge or self.cfg.bridge_id
        payload = {
            "bridge": bridge,
            "node": int(node),
            "ts": round(float(ts), 3),
            "fs": self.cfg.fs,
            "samples": _as_samples(samples),
            "rms": round(float(rms), 6),
            "flag": int(flag),
            "msg_id": _msg_id("acc"),
        }
        return self.publish(contract.TOPIC_ACCEL.format(bridge=bridge), payload)

    def publish_bhi(self, *, ts: float, bhi: float, u: float, cv: float, vib: float,
                    load: float, state: str, bridge: Optional[str] = None) -> bool:
        bridge = bridge or self.cfg.bridge_id
        payload = {
            "bridge": bridge,
            "ts": round(float(ts), 3),
            "bhi": float(bhi),
            "u": float(u),
            "cv": float(cv),
            "vib": float(vib),
            "load": float(load),
            "state": str(state),
            "msg_id": _msg_id("bhi"),
        }
        return self.publish(contract.TOPIC_BHI.format(bridge=bridge), payload, qos=contract.QOS_TELEMETRY)

    def publish_alert(self, *, severity: str, source: str, text: str,
                      recommendation: Optional[str] = None,
                      ts: Optional[float] = None, bridge: Optional[str] = None) -> bool:
        bridge = bridge or self.cfg.bridge_id
        payload = {
            "bridge": bridge,
            "ts": round(float(ts) if ts is not None else contract.now(), 3),
            "severity": severity,
            "source": source,
            "text": text,
            "recommendation": recommendation or "",
            "msg_id": _msg_id("alr"),
        }
        qos = contract.QOS_ALARM if severity == "critical" else contract.QOS_TELEMETRY
        return self.publish(contract.TOPIC_ALERT.format(bridge=bridge), payload, qos=qos)

    def publish_status(self, *, node: int, online: bool = True,
                       firmware: str = "vitish-edge-0.1", rssi: int = -62,
                       ts: Optional[float] = None, bridge: Optional[str] = None) -> bool:
        bridge = bridge or self.cfg.bridge_id
        payload = {
            "bridge": bridge,
            "node": int(node),
            "ts": round(float(ts) if ts is not None else contract.now(), 3),
            "online": bool(online),
            "firmware": firmware,
            "rssi": int(rssi),
            "msg_id": _msg_id("sta"),
        }
        return self.publish(contract.TOPIC_STATUS.format(bridge=bridge), payload)


# ---------------------------------------------------------------------------
# Subscriber
# ---------------------------------------------------------------------------
class Subscriber:
    """Subscribes to bridge topics and dispatches decoded JSON to handlers.

    ``handlers`` maps a topic (exact) to a callback ``cb(topic, payload_dict)``.
    If a ``default_handler`` is given, any unmatched topic is handed to it and
    the client subscribes to ``bridge/+/#``.
    """

    def __init__(self, cfg: Settings, handlers: Optional[Dict[str, Callable]] = None,
                 default_handler: Optional[Callable] = None) -> None:
        self.cfg = cfg
        self.handlers = dict(handlers or {})
        self.default_handler = default_handler
        self.connected = threading.Event()
        self._stop = threading.Event()
        cid = f"vitish-sub-{os.getpid()}-{random.randrange(1000, 9999)}"
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=cid
        )
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._thread: Optional[threading.Thread] = None

    def add_handler(self, topic: str, cb: Callable) -> None:
        self.handlers[topic] = cb

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        # paho 2.1.0: reason_code is a ReasonCode — use .value (int() raises TypeError)
        if getattr(reason_code, "value", -1) == 0:
            self.connected.set()
            topics = [(t, contract.QOS_TELEMETRY) for t in self.handlers]
            if self.default_handler is not None:
                topics.append(("bridge/+/#", contract.QOS_TELEMETRY))
            if topics:
                client.subscribe(topics)
            log.info("MQTT subscriber connected (%d topics)", len(topics))
        else:
            log.warning("MQTT subscriber connect refused: %s", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            payload = {"raw": msg.payload.decode("utf-8", errors="replace")}
        cb = self.handlers.get(msg.topic) or self.default_handler
        if cb is None:
            return
        try:
            cb(msg.topic, payload)
        except Exception:
            log.exception("subscriber handler error on %s", msg.topic)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._connect_loop, name="mqtt-subscriber", daemon=True
        )
        self._thread.start()

    def _connect_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.client.connect(
                    self.cfg.broker_host,
                    self.cfg.broker_port,
                    keepalive=self.cfg.mqtt_keepalive,
                )
                self.client.loop_forever()
            except Exception as exc:
                log.debug("subscriber connect failed: %s", exc)
            self.connected.clear()
            if self._stop.is_set():
                break
            time.sleep(2.0)

    def stop(self) -> None:
        self._stop.set()
        try:
            self.client.disconnect()
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def emit(topic: str, payload: dict, publisher: Optional[Publisher],
         bus=None, qos: int = contract.QOS_TELEMETRY) -> bool:
    """Standard producer helper.

    Publishes to MQTT; when the broker is unreachable, falls back to publishing
    directly on the event bus so the demo never depends on Docker being up.
    Because the MQTT subscriber is itself silent while the broker is down, the
    payload reaches consumers exactly once in both modes.
    """
    ok = publisher.publish(topic, payload, qos=qos) if publisher is not None else False
    if bus is not None and (publisher is None or not publisher.connected.is_set()):
        bus.publish(topic, payload, source="offline-fallback")
    return ok


def make_mqtt_router(bus):
    """Return a Subscriber.default_handler that forwards MQTT -> event bus.

    Telemetry topics are re-published under the same topic name. The internal
    control topic ``bridge/<id>/inject`` is re-published as ``control/cmd`` so
    a remote actor can drive the damage injector.
    """

    def route(topic: str, payload: dict) -> None:
        if topic.endswith("/inject"):
            bus.publish("control/cmd", payload, source="mqtt")
        else:
            bus.publish(topic, payload, source="mqtt")

    return route
