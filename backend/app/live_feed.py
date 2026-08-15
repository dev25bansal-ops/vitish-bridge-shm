"""
VITISH 2026 · PS#99 SHM — live public-broker ingestion adapter (demo).

Streams REAL structural telemetry from a public MQTT broker
(``test.mosquitto.org:1883``) onto the shared event bus, so the demo can show
genuine live ingestion alongside the Z24 replay.

Honesty rules (never violated — see vault/08-Startup/Company-Project.md §14):
- This is a *demo of live ingestion*, not owned telemetry. Public-broker
  publishers are third-party, unvetted and intermittent — ideal to prove
  ingestion, never presented as authoritative sensor data.
- Every emitted payload is tagged ``source='public-mosquitto'`` and
  ``bridge='live-demo'`` so it is never mistaken for hero-bridge ('z24')
  telemetry. The hero bridge and its verified BHI arc are untouched.
- Rate is trivially low (a few messages/second at most), so qos=0 and a
  lossy public broker are fine.

Contract note (ROADMAP lines 37/91): the feed publishes bridge-scoped event-bus
dicts under ``bridge/live-demo/...``, but the ``/accel`` row is a deliberately
THIN rms-only row — ``fs=0, samples=[]`` — because the public MSU feed
publishes RMS scalars only, never a raw 1024-sample waveform.  The frozen hero
``validate_accel`` would reject it; ``contract.validate_accel(row,
bridge='live-demo')`` accepts the thin row against its own expectations (see
contract.py).  The recorder persists the ``/accel`` rows (bridge='live-demo',
never fused into z24 BHI); the ``/telemetry`` envelopes are deliberately NOT
persisted and the WS bridge does NOT forward ``bridge/live-demo/#`` — the API
surfaces live status via REST ``/api/live`` (decision, ROADMAP line 91).
Topics verified live 2026-08-13:
``MSU/Accelerometer/{RMS,X,Y,Z,Vel,Disp}/LOC_MSU-*`` (structural condition-
monitoring node), ``MSU/Temperature|Humidity``, ``shm/usb3134a/data`` (1 Hz SHM
DAQ JSON), ``TiltSensor/#``, ``CNN/#`` (machinery vibration).
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt

from app import contract

log = logging.getLogger(__name__)

PUBLIC_BROKER = "test.mosquitto.org"
PUBLIC_PORT = 1883

# Namespaces we care about; everything else is dropped.
LIVE_TOPICS = [
    "MSU/Accelerometer/#",
    "MSU/Temperature/#",
    "MSU/Humidity/#",
    "shm/#",
    "TiltSensor/#",
    "CNN/#",
]

_AXIS_NODE = {"x": 1, "y": 2, "z": 3}  # MSU axes -> live-demo accel node numbers


def _num(payload: Any) -> Optional[float]:
    """Best-effort scalar extraction from the many public-broker payload styles."""
    if isinstance(payload, bool):
        return None
    if isinstance(payload, (int, float)):
        return float(payload)
    if isinstance(payload, str):
        try:
            return float(payload)
        except ValueError:
            return None
    if isinstance(payload, dict):
        for key in ("value", "val", "rms", "data", "reading", "v", "accel"):
            v = payload.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
    return None


class LiveFeed:
    """One dedicated paho client on the public broker -> event bus.

    ``bridge/live-demo/accel``      — one accel row per MSU RMS scalar (persisted).
    ``bridge/live-demo/telemetry``  — compact envelope for every other live value.
                                      Persistence + WS-surface decision (ROADMAP
                                      line 91): telemetry is observable on the BUS
                                      only — the WS bridge does not subscribe
                                      ``bridge/live-demo/#`` (no twin consumer; the
                                      twin reads live status via REST ``/api/live``)
                                      and the recorder deliberately does not persist
                                      it (unvetted third-party scalars; the thin
                                      accel rows already prove ingestion).

    Every source topic is rate-capped to one publish per ``rate_cap_s`` (default
    1.0 s), so a bursting publisher can't flood the bus or the recorder (ROADMAP
    line 91).  Skips are counted in ``rate_limited`` and surfaced in status().
    """

    def __init__(self, bus, *, broker_host: str = PUBLIC_BROKER,
                 broker_port: int = PUBLIC_PORT,
                 source: str = "public-mosquitto",
                 bridge: str = "live-demo",
                 rate_cap_s: float = 1.0) -> None:
        self.bus = bus
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.source = source
        self.bridge = bridge
        self.received = 0
        self.published = 0
        self.rate_cap_s = rate_cap_s  # 0 disables the cap
        self.rate_limited = 0
        self._last_pub: Dict[str, float] = {}
        self.last_topic: str = ""
        self.last_ts: float = 0.0
        self.connected = threading.Event()
        self._stop = threading.Event()
        cid = f"vitish-live-{os.getpid()}-{random.randrange(1000, 9999)}"
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=cid
        )
        self.client.reconnect_delay_set(min_delay=1, max_delay=15)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle ------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        # paho 2.1.0: reason_code is a ReasonCode — use .value (int() raises TypeError)
        if getattr(reason_code, "value", -1) == 0:
            self.connected.set()
            client.subscribe([(t, 0) for t in LIVE_TOPICS])
            log.info("live feed subscribed to %s:%d (%d topic patterns)",
                     self.broker_host, self.broker_port, len(LIVE_TOPICS))
        else:
            log.warning("live feed connect refused: %s", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        self.received += 1
        self.last_topic = msg.topic
        self.last_ts = contract.now()
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            payload = msg.payload.decode("utf-8", errors="replace")
        try:
            for topic, event in self._adapt(msg.topic, payload):
                # Per-source-topic rate cap (ROADMAP line 91): skip publishes on
                # a topic that already fired within rate_cap_s, so a bursting
                # publisher can't flood the bus/recorder. Distinct topics are
                # never limited, so the MSU batch (~12 s cadence) sails through.
                if self.rate_cap_s > 0:
                    prev = self._last_pub.get(msg.topic, 0.0)
                    if self.last_ts - prev < self.rate_cap_s:
                        self.rate_limited += 1
                        continue
                    self._last_pub[msg.topic] = self.last_ts
                    if len(self._last_pub) > 1024:  # prune: bounded topic set
                        stale = [t for t, ts in self._last_pub.items()
                                 if self.last_ts - ts > 60.0]
                        for t in stale:
                            del self._last_pub[t]
                self.published += 1
                self.bus.publish(topic, event, source=self.source)
        except Exception:
            log.exception("live feed adapt/publish failed on %s", msg.topic)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._connect_loop, name="live-feed", daemon=True
        )
        self._thread.start()

    def _connect_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.client.connect(self.broker_host, self.broker_port, keepalive=45)
                self.client.loop_forever()  # blocks; returns on disconnect
            except Exception as exc:
                log.debug("live feed connect failed: %s", exc)
            self.connected.clear()
            if self._stop.is_set():
                break
            time.sleep(3.0)

    def stop(self) -> None:
        self._stop.set()
        try:
            self.client.disconnect()
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self._thread and self._thread.is_alive()),
            "broker": f"{self.broker_host}:{self.broker_port}",
            "connected": self.connected.is_set(),
            "received": self.received,
            "published": self.published,
            "rate_limited": self.rate_limited,
            "rate_cap_s": self.rate_cap_s,
            "last_topic": self.last_topic,
            "last_ts": self.last_ts,
            "source": self.source,
            "bridge": self.bridge,
        }

    # -- namespace adapters ---------------------------------------------------
    def _adapt(self, topic: str, payload: Any) -> List[Tuple[str, dict]]:
        if topic.startswith("MSU/Accelerometer/RMS/"):
            axis = topic.split("/")[3].lower()
            value = _num(payload)
            if value is None:
                return []
            node = _AXIS_NODE.get(axis, 0)
            return [(
                f"bridge/{self.bridge}/accel",
                {"bridge": self.bridge, "node": node, "ts": contract.now(),
                 "fs": 0, "samples": [], "rms": round(value, 6), "flag": 0,
                 "source": self.source, "source_topic": topic},
            )]
        if topic.startswith("MSU/Accelerometer/"):  # Vel/Disp scalars
            parts = topic.split("/")
            return [self._telemetry(topic, {
                "metric": parts[3].lower(),
                "axis": parts[4].lower() if len(parts) > 4 else "",
                "value": _num(payload),
            })]
        if topic.startswith("MSU/Temperature/") or topic.startswith("MSU/Humidity/"):
            metric = topic.split("/")[1].lower()
            return [self._telemetry(topic, {"metric": metric, "value": _num(payload)})]
        if topic.startswith("shm/"):
            data = payload if isinstance(payload, dict) else {"raw": payload}
            return [self._telemetry(topic, {"metric": "daq", "data": data})]
        if topic.startswith("TiltSensor/"):
            return [self._telemetry(topic, {"metric": "tilt", "value": _num(payload),
                                            "data": payload})]
        if topic.startswith("CNN/"):
            return [self._telemetry(topic, {"metric": "machinery-vib", "data": payload})]
        return []

    def _telemetry(self, source_topic: str, fields: dict) -> Tuple[str, dict]:
        event = {"bridge": self.bridge, "ts": contract.now(),
                 "source": self.source, "source_topic": source_topic, **fields}
        return (f"bridge/{self.bridge}/telemetry", event)


# ---------------------------------------------------------------------------
# process-wide handle so the API can report live-feed status without coupling
# ---------------------------------------------------------------------------
_live_feed: Optional[LiveFeed] = None


def set_live_feed(feed: Optional[LiveFeed]) -> None:
    global _live_feed
    _live_feed = feed


def get_live_feed() -> Optional[LiveFeed]:
    return _live_feed
