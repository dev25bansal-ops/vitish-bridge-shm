"""
Real-hardware edge-node monitor (edge slot bridges; default 'esp32-1' + 'esp01-1').

The ESP32 / ESP-01S node firmware publishes contract-shaped telemetry to the
local MQTT broker on ``bridge/<id>/accel`` (+ ``bridge/<id>/status``), where
``<id>`` is one of ``EDGE_BRIDGES`` (firmware/esp32 -> ``esp32-1``,
firmware/esp01 -> ``esp01-1``).  The backend's existing subscriber already
routes ``bridge/+/#`` onto the shared event bus, so this monitor just listens on
the bus — no new ingestion path, no coupling to the z24 hero arc.  The monitor
and the edge recorder subscribe to EVERY edge bridge id (S8 fix: a stock-flashed
ESP-01S was silently ignored because the monitor only listened for esp32-1).

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
import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Iterable, Optional

from app import contract

log = logging.getLogger(__name__)

# Edge-node slot(s) the backend monitors.  Both committed firmware targets are
# stock-flashed to one of these ids, so a stock ESP-01S is NOT silently ignored:
# the monitor + edge recorder subscribe to every id here.  Override per pilot
# with VITISH_EDGE_BRIDGES (comma-separated).
_DEFAULT_EDGE_BRIDGES = ("esp32-1", "esp01-1")
EDGE_BRIDGES: tuple[str, ...] = tuple(
    b.strip() for b in
    os.environ.get("VITISH_EDGE_BRIDGES", ",".join(_DEFAULT_EDGE_BRIDGES)).split(",")
    if b.strip()) or _DEFAULT_EDGE_BRIDGES
EDGE_BRIDGE = EDGE_BRIDGES[0]      # primary edge slot (manifest / back-compat)
EDGE_HARDWARE = "ESP32 DevKit (CP2102) - ESP32-WROOM-32, 4 MB flash"
ESP01_HARDWARE = "ESP-01S (ESP8266EX, 1 MB flash) — no ADC, BIST tone only"
STALE_S = 8.0          # node publishes ~1 Hz; offline after 8 s of silence
_RECENT_MAX = 120


class EdgeNodeMonitor:
    """Last-known state of the real edge nodes, fed by the shared event bus.

    State is tracked PER edge bridge id (esp32-1 / esp01-1 / configured set) so
    `/api/bridge/<id>/state` returns the right node and a stock ESP-01S is not
    silently ignored by a monitor that only watched esp32-1.
    """

    def __init__(self, bus, bridges: Iterable[str] = EDGE_BRIDGES,
                 stale_s: float = STALE_S) -> None:
        self.bus = bus
        self.bridges: tuple[str, ...] = tuple(bridges)
        self.stale_s = stale_s
        self._lock = threading.Lock()
        self._state: Dict[str, Dict[str, Any]] = {
            b: {"received": 0, "last_seen": 0.0, "last": {},
                "recent": deque(maxlen=_RECENT_MAX)}
            for b in self.bridges
        }
        self._tokens: list[int] = []

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        if not self._tokens:
            for b in self.bridges:
                self._tokens.append(self.bus.subscribe(
                    f"bridge/{b}/#", self._on_event))

    def stop(self) -> None:
        for tok in self._tokens:
            self.bus.unsubscribe(tok)
        self._tokens = []

    # -- bus -> status ----------------------------------------------------------
    def _on_event(self, topic: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        parts = topic.split("/")
        b = parts[1] if len(parts) > 1 and parts[0] == "bridge" else None
        st = self._state.get(b)
        if st is None:  # not an edge bridge this monitor watches
            return
        with self._lock:
            st["received"] += 1
            st["last_seen"] = contract.now()
            if topic.endswith("/accel"):
                st["last"] = {**payload, "_kind": "accel"}
                if payload.get("rms") is not None:
                    st["recent"].append(
                        (payload.get("ts"), payload.get("rms"), payload.get("flag")))
            elif topic.endswith("/status"):
                # heartbeat — the accel record is richer (rssi/heap/uptime/fw);
                # only refresh rssi if it arrives fresh and don't clobber accel.
                if payload.get("rssi") is not None and st["last"].get("_kind") == "accel":
                    st["last"]["rssi"] = payload.get("rssi")

    # -- API ---------------------------------------------------------------------
    def status(self, bridge: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Status for one edge bridge (default: most recently active, else primary).

        Returns None when `bridge` is not a monitored edge id.
        """
        now = contract.now()
        with self._lock:
            if bridge is None:
                active = [b for b, st in self._state.items() if st["received"] > 0]
                bridge = (max(active, key=lambda b: self._state[b]["last_seen"])
                          if active else self.bridges[0])
            st = self._state.get(bridge)
            if st is None:
                return None
            online = st["received"] > 0 and (now - st["last_seen"]) <= self.stale_s
            last = dict(st["last"])
            recent = [{"ts": r[0], "rms": r[1], "flag": r[2]} for r in st["recent"]]
            received = st["received"]
            last_seen = st["last_seen"]
        fw = last.get("fw") or ""
        # honest hardware label: the actual reporting device (fw/source name it),
        # never a fixed "ESP32" claim for an ESP-01S filling the same slot.
        hardware = (ESP01_HARDWARE
                    if bridge == "esp01-1" or fw.startswith("vitish-edge-esp01")
                    else EDGE_HARDWARE)
        return {
            "enabled": True,
            "bridge": bridge,
            "online": online,
            "hardware": hardware,
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


def get_edge_status(bridge: Optional[str] = None) -> Optional[dict]:
    return _edge.status(bridge) if _edge is not None else None
