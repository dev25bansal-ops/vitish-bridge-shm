"""
VITISH 2026 · PS#99 SHM — shared in-process pub/sub event bus.

This is the glue that lets the simulator, MQTT subscriber, fusion service,
persistence recorder, WebSocket bridge, API and demo driver share one stream
without import-time coupling.

Topic conventions
-----------------
* Telemetry topics mirror MQTT topic names, e.g. ``bridge/z24/accel``.
* Internal control topics use the ``control/`` prefix, e.g. ``control/cmd``
  (a single JSON dict with a ``cmd`` field) and ``control/status``.

Pattern matching is MQTT-style: ``+`` matches one level, ``#`` matches the
remaining levels (only valid as the final level).
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, List, Optional, Tuple

log = logging.getLogger(__name__)


def _match(pattern: str, topic: str) -> bool:
    pp = pattern.split("/")
    tt = topic.split("/")
    for i, p in enumerate(pp):
        if p == "#":
            return True
        if p == "+":
            continue
        if i >= len(tt) or p != tt[i]:
            return False
    return len(pp) == len(tt)


class EventBus:
    """Thread-safe minimal pub/sub. Callbacks run in the publisher's thread."""

    def __init__(self) -> None:
        self._subs: List[Tuple[str, Callable[[str, Any], None], int]] = []
        self._lock = threading.RLock()
        self._seq = 0

    def subscribe(self, pattern: str, callback: Callable[[str, Any], None]) -> int:
        """Subscribe to a topic pattern; returns a token for unsubscribe()."""
        with self._lock:
            self._seq += 1
            token = self._seq
            self._subs.append((pattern, callback, token))
        log.debug("bus subscribe '%s' token=%s", pattern, token)
        return token

    def unsubscribe(self, token: int) -> None:
        with self._lock:
            self._subs = [s for s in self._subs if s[2] != token]

    def publish(self, topic: str, payload: Any = None, source: str | None = None) -> int:
        """Publish an event. Returns the number of subscribers invoked.

        Callbacks are snapshotted under the lock then invoked OUTSIDE it so a
        callback that itself publishes cannot deadlock.
        """
        with self._lock:
            targets = [cb for (p, cb, _) in self._subs if _match(p, topic)]
        n = 0
        for cb in targets:
            try:
                cb(topic, payload)
                n += 1
            except Exception:  # one bad consumer must not kill the stream
                log.exception("bus callback error on topic '%s'", topic)
        return n

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)


_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_bus() -> EventBus:
    """Return the process-wide singleton event bus (created lazily)."""
    global _bus
    with _bus_lock:
        if _bus is None:
            _bus = EventBus()
        return _bus
