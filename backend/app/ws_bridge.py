"""
VITISH 2026 · PS#99 SHM — WebSocket bridge (ws://localhost:8765).

The digital twin's live data path.  It fans the shared event bus out to every
connected browser:

* subscribes to ``bridge/<id>/#`` on the event bus
* each client receives one JSON object per event::

      {"topic": "bridge/z24/accel", "bridge": "z24", "node": 7, "ts": ..., "samples": [...], ...}

  i.e. the contract payload with a leading ``topic`` field so the twin can
  switch renderers.

The bus callback runs on the MQTT thread, so delivery to asyncio clients is
scheduled with ``loop.call_soon_threadsafe`` — no locks are held while writing
to sockets.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Dict, Optional

import websockets

from app import __version__, contract
from app.config import Settings

log = logging.getLogger(__name__)


class WSBridge:
    def __init__(self, cfg: Settings, bus, scenario: str = "healthy",
                 store=None) -> None:
        self.cfg = cfg
        self.bus = bus
        # Optional persistence store; when present, freshly-connected clients get
        # an alert catch-up (item 7, ROADMAP-NEXT) so a reload mid-arc never
        # shows an empty AlertsPanel.
        self.store = store
        self._clients: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_fut: Optional[asyncio.Future] = None
        self._sub_token: Optional[int] = None
        self._cmd_token: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self.bound_port: Optional[int] = None  # actual port after bind (may fall back)
        # last known storyboard scenario (healthy|rupture), read from the
        # control/cmd stream and replayed to freshly-connected clients so the
        # twin never shows "SYSTEM NOMINAL" after a reload mid-arc.
        self._scenario = scenario if scenario in ("healthy", "rupture") else "healthy"

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="ws-bridge", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        """Bind on the configured port, walking upward if it is taken."""
        self._loop = asyncio.get_running_loop()
        for port in range(self.cfg.ws_port, self.cfg.ws_port + 20):
            try:
                async with websockets.serve(
                    self._handler, self.cfg.ws_host, port, max_size=8_000_000
                ) as server:
                    self.bound_port = port
                    self._sub_token = self.bus.subscribe(
                        f"bridge/{self.cfg.bridge_id}/#", self._on_bus_event)
                    # forward the storyboard control channel too (the demo
                    # driver / API publish {cmd: scenario} there at t=75)
                    self._cmd_token = self.bus.subscribe(
                        "control/cmd", self._on_bus_event)
                    log.info("WS bridge listening on ws://%s:%d",
                             self.cfg.ws_host, port)
                    self._stop_fut = self._loop.create_future()
                    try:
                        await self._stop_fut
                    except (asyncio.CancelledError, Exception):
                        pass
                    finally:
                        if self._sub_token is not None:
                            self.bus.unsubscribe(self._sub_token)
                        if self._cmd_token is not None:
                            self.bus.unsubscribe(self._cmd_token)
                        with self._lock:
                            self._clients.clear()
                        log.info("WS bridge stopped")
                    return
            except OSError as exc:
                log.warning("WS bridge: port %d busy (%s), trying next", port, exc)
        log.error("WS bridge: no free port in [%d, %d)",
                  self.cfg.ws_port, self.cfg.ws_port + 20)

    def stop(self) -> None:
        if self._loop is not None and self._stop_fut is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop_fut.set_result, True)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    # -- bus -> clients --------------------------------------------------------
    def _on_bus_event(self, topic: str, payload: Any) -> None:
        if topic == "control/cmd" and isinstance(payload, dict) \
                and payload.get("cmd") == "scenario" \
                and payload.get("scenario") in ("healthy", "rupture"):
            with self._lock:
                self._scenario = payload["scenario"]
        envelope = {"topic": topic}
        if isinstance(payload, dict):
            envelope.update(payload)
        else:
            envelope["payload"] = payload
        text = json.dumps(envelope)
        with self._lock:
            clients = list(self._clients.values())
        for c in clients:
            try:
                # QueueFull would otherwise fire INSIDE the event loop (uncaught)
                # when a slow/backgrounded tab falls behind -> silently missing
                # the BHI band-crossing. Drop-oldest keeps the newest frame.
                self._loop.call_soon_threadsafe(self._enqueue, c["queue"], text)
            except Exception:
                pass

    def _enqueue(self, q: asyncio.Queue, text: str) -> None:
        """Push a frame to a client queue, dropping the oldest frame when full."""
        try:
            if q.full():
                q.get_nowait()
                log.warning("WS bridge: client queue full — dropped oldest frame")
            q.put_nowait(text)
        except Exception:
            pass

    # -- per-client handler ------------------------------------------------------
    async def _handler(self, conn) -> None:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        cid = id(conn)
        with self._lock:
            self._clients[cid] = {"queue": q}
        hello = json.dumps({
            "topic": "hello",
            "service": "vitish-ws-bridge",
            "version": __version__,
            "ts": contract.now(),
        })
        # catch-up: a client connecting mid-arc must learn the current storyboard
        # scenario (the cmd fires once at t=75 and would otherwise be missed).
        with self._lock:
            scenario = self._scenario
        catchup = json.dumps({
            "topic": "control/cmd",
            "cmd": "scenario",
            "scenario": scenario,
            "source": "ws-snapshot",
        })
        # Alert catch-up: replay the last few persisted alerts (oldest first) so
        # a reload mid-arc doesn't show an empty AlertsPanel.  Honest failure:
        # if the store is missing or down, we simply skip the replay.
        alert_frames = self._alert_catchup()
        try:
            await conn.send(hello)
            await conn.send(catchup)
            for f in alert_frames:
                await conn.send(f)
            await asyncio.gather(self._sender(conn, q), self._reader(conn))
        except Exception:
            pass
        finally:
            with self._lock:
                self._clients.pop(cid, None)
            try:
                await conn.close()
            except Exception:
                pass

    def _alert_catchup(self, limit: int = 8) -> list:
        """Replay recent alerts as normal bridge/<id>/alert frames (oldest first)."""
        if self.store is None or not hasattr(self.store, "recent_alerts"):
            return []
        try:
            rows = self.store.recent_alerts(self.cfg.bridge_id, limit=limit)
        except Exception:
            log.warning("WS bridge: alert catch-up unavailable (store down)")
            return []
        frames = []
        for r in rows:
            try:
                frame = {
                    "topic": contract.TOPIC_ALERT.format(bridge=self.cfg.bridge_id),
                    "bridge": self.cfg.bridge_id,
                    "ts": float(r.get("ts") or contract.now()),
                    "severity": str(r.get("severity") or "info"),
                    "source": str(r.get("source") or "fusion"),
                    "text": str(r.get("text") or ""),
                    "recommendation": str(r.get("recommendation") or ""),
                    "ws_snapshot": True,
                }
                frames.append(json.dumps(frame))
            except Exception:
                continue
        return frames

    async def _sender(self, conn, q: asyncio.Queue) -> None:
        while True:
            text = await q.get()
            await conn.send(text)

    async def _reader(self, conn) -> None:
        try:
            while True:
                await conn.recv()  # twin may send anything; we ignore it
        except Exception:
            return


# ---------------------------------------------------------------------------
# process-wide handle so the API / config can report the ACTUAL bound port
# (run_all.py walks ws_port upward when the default is taken)
# ---------------------------------------------------------------------------
_current: Optional["WSBridge"] = None


def set_current_bridge(b: Optional["WSBridge"]) -> None:
    global _current
    _current = b


def get_bound_port() -> Optional[int]:
    if _current is None:
        return None
    with _current._lock:
        return _current.bound_port
