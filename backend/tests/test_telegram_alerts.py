"""
Out-of-band alert dispatch gate — Telegram v1 (NEW-01).

Proves the dispatcher is optional (disabled without token+chat), subscribes to
``bridge/+/alert`` on the real shared event bus, forwards threshold-crossing
alerts to a transport (here a captured fake) with honest formatting, filters by
severity, throttles per (bridge, severity), and FAIL-OPENS: a raising transport
is logged and swallowed, never propagating into the bus loop.

Run:  python backend/tests/test_telegram_alerts.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import telegram_alerts as tg_mod  # noqa: E402
from app.events import get_bus  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: List[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


class _Capture:
    """Fake transport: records every (text) it would send."""

    def __init__(self) -> None:
        self.texts: List[str] = []

    def send(self, disp, token: str, text: str) -> None:
        self.texts.append(text)


def _alert(severity: str = "critical", source: str = "fusion",
           text: str = "BHI dropped to RED", rec: str = "Restrict traffic",
           bridge: str = "z24") -> dict:
    return {"bridge": bridge, "ts": time.time(), "severity": severity,
            "source": source, "text": text, "recommendation": rec}


def test_disabled_without_creds() -> None:
    print("[1] disabled without token/chat (fail-safe default)")
    cap = _Capture()
    d = tg_mod.TelegramAlertDispatcher(get_bus(), token="", chat_id="",
                                       transport=cap.send)
    check("enabled False", d.enabled is False)
    sent = d.dispatch("bridge/z24/alert", _alert())
    check("dispatch returns False", sent is False)
    check("no transport call", len(cap.texts) == 0)
    st = d.status()
    check("status enabled False", st["enabled"] is False)


def test_dispatches_critical_on_bus() -> None:
    print("[2] real bus wiring + critical dispatch + honest format")
    bus = get_bus()
    cap = _Capture()
    d = tg_mod.TelegramAlertDispatcher(bus, token="TESTTOKEN", chat_id="12345",
                                       throttle_s=0.0, transport=cap.send)
    d.start()
    try:
        bus.publish("bridge/z24/alert", _alert(), source="test")
        time.sleep(0.05)
        check("transport called once", len(cap.texts) == 1)
        if cap.texts:
            t = cap.texts[0]
            check("text names bridge", "bridge z24" in t)
            check("text has severity", "critical" in t.lower())
            check("text has source", "fusion" in t)
            check("text has alert body", "BHI dropped to RED" in t)
            check("text has recommendation", "Restrict traffic" in t)
            check("text has footer", "VITISH SHM" in t)
        st = d.status()
        check("status enabled True", st["enabled"] is True)
        check("status sent count", st["sent"] == 1)
    finally:
        d.stop()


def test_min_severity_filter() -> None:
    print("[3] severity filter (info skipped at min=warning)")
    cap = _Capture()
    d = tg_mod.TelegramAlertDispatcher(get_bus(), token="T", chat_id="1",
                                       min_severity="warning", throttle_s=0.0,
                                       transport=cap.send)
    check("info skipped", d.dispatch("bridge/z24/alert", _alert("info")) is False)
    check("warning passes", d.dispatch("bridge/z24/alert", _alert("warning")) is True)
    check("critical passes", d.dispatch("bridge/z24/alert", _alert("critical")) is True)
    check("two messages sent", len(cap.texts) == 2)

    cap2 = _Capture()
    d2 = tg_mod.TelegramAlertDispatcher(get_bus(), token="T", chat_id="1",
                                        min_severity="critical", throttle_s=0.0,
                                        transport=cap2.send)
    check("warning skipped at min=critical",
          d2.dispatch("bridge/z24/alert", _alert("warning")) is False)
    check("critical passes at min=critical",
          d2.dispatch("bridge/z24/alert", _alert("critical")) is True)
    check("one message sent (critical only)", len(cap2.texts) == 1)


def test_throttle_per_bridge_severity() -> None:
    print("[4] throttle per (bridge, severity)")
    cap = _Capture()
    d = tg_mod.TelegramAlertDispatcher(get_bus(), token="T", chat_id="1",
                                       throttle_s=60.0, transport=cap.send)
    check("first critical sent", d.dispatch("bridge/z24/alert", _alert()) is True)
    check("second critical throttled",
          d.dispatch("bridge/z24/alert", _alert()) is False)
    check("warning not throttled by critical key",
          d.dispatch("bridge/z24/alert", _alert("warning")) is True)
    check("different bridge not throttled",
          d.dispatch("bridge/esp32-1/alert", _alert(bridge="esp32-1")) is True)
    check("three messages total", len(cap.texts) == 3)


def test_fail_open_transport_error() -> None:
    print("[5] fail-open: raising transport swallowed by bus callback")
    bus = get_bus()

    def boom(disp, token, text):
        raise RuntimeError("network down")

    d = tg_mod.TelegramAlertDispatcher(bus, token="T", chat_id="1",
                                       throttle_s=0.0, transport=boom)
    d.start()
    try:
        # must not raise through the bus callback
        bus.publish("bridge/z24/alert", _alert(), source="test")
        time.sleep(0.05)
        st = d.status()
        check("dispatcher alive after transport error", st["enabled"] is True)
        check("no message counted (send failed)", st["sent"] == 0)
    finally:
        d.stop()


def main() -> int:
    test_disabled_without_creds()
    test_dispatches_critical_on_bus()
    test_min_severity_filter()
    test_throttle_per_bridge_severity()
    test_fail_open_transport_error()
    print(f"\ntelegram-alerts gate: {PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILURES:")
        for f in FAILURES:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
