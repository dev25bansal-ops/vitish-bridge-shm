"""
Real-hardware edge-node monitor (bridge='esp32-1').

The ESP32 node publishes contract-shaped telemetry to the local MQTT broker
on ``bridge/esp32-1/accel`` (+ ``bridge/esp32-1/status``).  The backend's
existing subscriber already routes ``bridge/+/#`` onto the shared event bus, so
this monitor just listens on the bus — no new ingestion path, no coupling to
the z24 hero arc.

Honesty (the LIVE badge must show these labels, never a stronger claim):
  * The edge node has NO accelerometer attached — the accel window is a
    deterministic SELF-TEST / BIST tone; the payload carries
    ``signal_kind: "self-test-bist"`` and this module surfaces it.
  * Real measured quantities ARE reported: WiFi RSSI (dBm), free heap (bytes),
    uptime (s) and a wall-clock ts (NTP when reachable).
  * This is a separate bridge id — it is NEVER fused into the z24 BHI.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

from app import contract

log = logging.getLogger(__name__)

EDGE_BRIDGE = "esp32-1"
EDGE_HARDWARE = "ESP32 DevKit (CP2102) - ESP32-WROOM-32, 4 MB flash"
STALE_S = 8.0          # node publishes ~1 Hz; offline after 8 s of silence
_RECENT_MAX = 120


class EdgeNodeMonitor:
    """Last-known state of the real edge node, fed by the shared event bus."""

    def __init__(self, bus, bridge: str = EDGE_BRIDGE, stale_s: float = STALE_S) -> None:
        self.bus = bus
        self.bridge = bridge
        self.stale_s = stale_s
        self.received = 0
        self.last_seen = 0.0
        self._lock = threading.Lock()
        self._last: Dict[str, Any] = {}
        self._recent: Deque[tuple] = deque(maxlen=_RECENT_MAX)  # (ts, rms, flag)
        self._token: Optional[int] = None

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        if self._token is None:
            self._token = self.bus.subscribe(
                f"bridge/{self.bridge}/#", self._on_event)

    def stop(self) -> None:
        if self._token is not None:
            self.bus.unsubscribe(self._token)
            self._token = None

    # -- bus -> status ----------------------------------------------------------
    def _on_event(self, topic: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        with self._lock:
            self.received += 1
            self.last_seen = contract.now()
            if topic.endswith("/accel"):
                self._last = {**payload, "_kind": "accel"}
                if payload.get("rms") is not None:
                    self._recent.append(
                        (payload.get("ts"), payload.get("rms"), payload.get("flag")))
            elif topic.endswith("/status"):
                # heartbeat — the accel record is richer (rssi/heap/uptime/fw);
                # only refresh rssi if it arrives fresh and don't clobber accel.
                if payload.get("rssi") is not None and self._last.get("_kind") == "accel":
                    self._last["rssi"] = payload.get("rssi")

    # -- API ---------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        now = contract.now()
        with self._lock:
            online = self.received > 0 and (now - self.last_seen) <= self.stale_s
            last = dict(self._last)
            recent = [{"ts": r[0], "rms": r[1], "flag": r[2]} for r in self._recent]
            received = self.received
            last_seen = self.last_seen
        return {
            "enabled": True,
            "bridge": self.bridge,
            "online": online,
            "hardware": EDGE_HARDWARE,
            "received": received,
            "last_seen_ago_s": round(now - last_seen, 1) if received else None,
            "signal_kind": last.get("signal_kind", "self-test-bist"),
            "accel": {
                "rms": last.get("rms"),
                "flag": last.get("flag"),
                "fs": last.get("fs"),
                "samples_n": len(last.get("samples") or []),
            },
            "rssi_dbm": last.get("rssi"),
            "heap_bytes": last.get("heap"),
            "uptime_s": last.get("uptime_s"),
            "fw": last.get("fw"),
            "ts": last.get("ts"),
            "recent_rms": recent[-60:],
            "hero_bridge_untouched": True,
            "honesty": {
                "real_hardware": True,
                "accel_is": ("self-test BIST tone — no accelerometer attached "
                             "to the edge node; plug an I2C ADXL345/MPU-6050 in "
                             "to stream real vibration"),
                "real_measured": [
                    "WiFi RSSI (dBm)", "free heap (bytes)", "uptime (s)",
                    "wall-clock ts (NTP when reachable)",
                ],
                "note": "real WiFi + MQTT transport; accel content is a labeled "
                        "self-test signal, never real bridge vibration",
            },
        }


# ---------------------------------------------------------------------------
# process-wide handle so the API / manifest can read status without coupling
# ---------------------------------------------------------------------------
_edge: Optional[EdgeNodeMonitor] = None


def set_edge_monitor(m: Optional[EdgeNodeMonitor]) -> None:
    global _edge
    _edge = m


def get_edge_monitor() -> Optional[EdgeNodeMonitor]:
    return _edge


def get_edge_status() -> Optional[dict]:
    return _edge.status() if _edge is not None else None
