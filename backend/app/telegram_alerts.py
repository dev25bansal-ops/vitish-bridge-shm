"""
Out-of-band alert dispatch — Telegram v1 (NEW-01, COMPREHENSIVE-ANALYSIS 7.6 item 3).

Subscribes to the alert topic (``bridge/<id>/alert``, contract TOPIC_ALERT) on
the shared event bus and forwards threshold-crossing alerts to a Telegram chat
via the Bot API.  Deliberately OPTIONAL and fail-open:

  * enabled ONLY when ``VITISH_TELEGRAM_TOKEN`` + ``VITISH_TELEGRAM_CHAT`` are
    set; otherwise it is a silent no-op (zero coupling to the demo arc).
  * any send failure (network, bad token, API not-ok) is logged and swallowed —
    a misconfigured dispatcher can never take the backend down or stall the
    bus loop.
  * throttled per (bridge, severity): a burst of alerts becomes one message.
  * honest by construction: it forwards the alert's OWN fields (bridge, ts,
    severity, source, text, recommendation) and a fixed footer.  It never
    fabricates urgency, a location, or an RUL.  ``run_all`` passes a demo
    footer when ``--demo`` so an out-of-band ping during the story arc is
    labeled "simulated PS#99 demo pipeline — not real bridge telemetry".

Transport is stdlib urllib (JSON POST to ``/bot<token>/sendMessage``) — no new
dependency, no async, no state beyond the throttle map.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

TOKEN_ENV = "VITISH_TELEGRAM_TOKEN"
CHAT_ENV = "VITISH_TELEGRAM_CHAT"
_DEFAULT_TOKEN = os.environ.get(TOKEN_ENV, "") or None
_DEFAULT_CHAT = os.environ.get(CHAT_ENV, "") or None

SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
THROTTLE_S = 30.0          # one message per (bridge, severity) per window
SEND_TIMEOUT_S = 5.0
_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramAlertDispatcher:
    """Bus listener -> throttled Telegram Bot API dispatcher (fail-open)."""

    def __init__(
        self,
        bus,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        min_severity: str = "warning",
        throttle_s: float = THROTTLE_S,
        footer: Optional[str] = None,
        transport: Optional[Callable[["TelegramAlertDispatcher", str, str], None]] = None,
    ) -> None:
        self.bus = bus
        # explicit "" disables (never falls back to env); None falls back to env
        self.token = token if token is not None else _DEFAULT_TOKEN
        self.chat_id = chat_id if chat_id is not None else _DEFAULT_CHAT
        self.min_severity = min_severity
        self.throttle_s = throttle_s
        self.footer = footer or "— VITISH SHM alert dispatcher"
        self._transport = transport or self._default_send
        self._lock = threading.Lock()
        self._last_sent: Dict[tuple, float] = {}
        self._sent = 0
        self._tokens: list[int] = []

    # -- lifecycle ------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def start(self) -> None:
        if not self._tokens and self.enabled:
            self._tokens.append(
                self.bus.subscribe("bridge/+/alert", self._on_alert))
            log.info("telegram alert dispatch ENABLED -> chat %s",
                     self._chat_label())

    def stop(self) -> None:
        for tok in self._tokens:
            self.bus.unsubscribe(tok)
        self._tokens = []

    # -- bus -> dispatch --------------------------------------------------------
    def _on_alert(self, topic: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        try:
            self.dispatch(topic, payload)
        except Exception:
            # fail-open: never let a Telegram hiccup raise into the bus loop
            log.exception("telegram dispatch failed on %s", topic)

    def dispatch(self, topic: str, payload: dict) -> bool:
        """Forward one alert; return True when a message was actually sent."""
        if not self.enabled:
            return False
        severity = str(payload.get("severity", "")).lower()
        rank = SEVERITY_RANK.get(severity)
        min_rank = SEVERITY_RANK.get(self.min_severity, 1)
        if rank is None or rank < min_rank:
            return False

        # The topic names the bridge (bridge/<id>/alert) and is authoritative,
        # mirroring the recorder's identity boundary (ROADMAP line 38): a payload
        # claiming a different bridge on this topic is inconsistent.  We key the
        # throttle + the message on the TOPIC bridge so the recipient is told
        # which bus topic carried the alert.
        bridge = self._bridge_from_topic(topic)
        if bridge == "unknown":
            bridge = payload.get("bridge") or "unknown"
        if bridge != payload.get("bridge") and payload.get("bridge"):
            log.warning("telegram alert bridge mismatch: topic=%s payload=%s",
                        topic, payload.get("bridge"))
        key = (bridge, severity)
        now = time.monotonic()
        with self._lock:
            if now - self._last_sent.get(key, 0.0) < self.throttle_s:
                log.info("telegram throttled %s/%s (%.0fs window)",
                         bridge, severity, self.throttle_s)
                return False
            self._last_sent[key] = now

        text = self._format(payload, bridge)
        try:
            self._transport(self, self.token, text)
        except Exception:
            log.exception("telegram transport failed for %s/%s", bridge, severity)
            return False
        with self._lock:
            self._sent += 1
        log.info("telegram dispatched %s/%s (total %d)", bridge, severity, self._sent)
        return True

    # -- formatting --------------------------------------------------------------
    def _format(self, payload: dict, bridge: str) -> str:
        tag = "ALERT" if payload.get("severity") == "critical" else "alert"
        lines = [
            f"[{tag}] VITISH SHM — bridge {bridge}",
            f"severity: {payload.get('severity')} · source: {payload.get('source')}",
            str(payload.get("text") or "").strip(),
        ]
        rec = str(payload.get("recommendation") or "").strip()
        if rec:
            lines.append(f"recommendation: {rec}")
        lines.append(self.footer)
        return "\n".join(line for line in lines if line)

    # -- transport ----------------------------------------------------------------
    def _default_send(self, token: str, text: str) -> None:
        """stdlib Bot-API call.  Raises on network error; not-ok is logged."""
        url = _API.format(token=token)
        body = json.dumps({"chat_id": self.chat_id, "text": text,
                           "disable_web_page_preview": True}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=SEND_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {}
        if not parsed.get("ok"):
            log.warning("telegram API returned not-ok: %.200s", raw)

    # -- helpers ------------------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            sent = self._sent
        return {"enabled": self.enabled, "min_severity": self.min_severity,
                "chat": self._chat_label(), "sent": sent,
                "throttle_s": self.throttle_s}

    def _chat_label(self) -> str:
        c = str(self.chat_id or "")
        return c if len(c) <= 8 else c[:4] + "…" + c[-2:]

    @staticmethod
    def _bridge_from_topic(topic: str) -> str:
        parts = topic.split("/")
        return parts[1] if len(parts) > 1 and parts[0] == "bridge" else "unknown"


# ---------------------------------------------------------------------------
# process-wide handle so run_all / banner can read status without coupling
# ---------------------------------------------------------------------------
_disp: Optional[TelegramAlertDispatcher] = None


def set_dispatcher(d: Optional[TelegramAlertDispatcher]) -> None:
    global _disp
    _disp = d


def get_dispatcher() -> Optional[TelegramAlertDispatcher]:
    return _disp


def get_status() -> Optional[dict]:
    return _disp.status() if _disp is not None else None
