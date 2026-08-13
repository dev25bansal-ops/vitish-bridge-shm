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
    def __init__(self, cfg: Settings, bus) -> None:
        self.cfg = cfg
        self.bus = bus
        self._clients: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_fut: Optional[asyncio.Future] = None
        self._sub_token: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self.bound_port: Optional[int] = None  # actual port after bind (may fall back)

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
                self._loop.call_soon_threadsafe(c["queue"].put_nowait, text)
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
        try:
            await conn.send(hello)
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
