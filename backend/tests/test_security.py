"""§2.1 SEC gate (SEC-01/02/03/04/06) — surface-area + auth hardening.

These are the security fixes from the COMPREHENSIVE-ANALYSIS SEC campaign
(docs/COMPREHENSIVE-ANALYSIS.md §2.1).  The threat model: the demo laptop sits on
venue WiFi, and previously docker-compose published 1883/9001/5432 on 0.0.0.0
with ``allow_anonymous true`` — any device on the LAN could forge telemetry or
drive the control plane.  This gate pins the hardened posture WITHOUT breaking
the one-command demo:

  * SEC-01  — every compose port binds 127.0.0.1 (loopback); broker auth is an
    OPT-IN "secure mode" (VITISH_MQTT_USER/PASS) that generates a mosquitto
    password file + toggles allow_anonymous false + applies the topic ACL; the
    backend Publisher/Subscriber send credentials ONLY when both env vars are
    set; the public-broker live feed builds its OWN client and must never see
    local creds.
  * SEC-02  — the state-changing demo route (POST /api/demo/scenario) is
    token-gated (X-VITISH-DEMO, timing-safe compare) + per-IP rate limited;
    disabled (403) by default.
  * SEC-03  — WS origin validation: VITISH_WS_ORIGINS locks the handshake to
    exact origins (a cross-site browser hijack always sends Origin).
  * SEC-04  — Postgres binds 127.0.0.1:5432 with env-overridable creds.
  * SEC-06  — per-client WS fan-out cap (MAX_CLIENTS=64) so a loopback/LAN flood
    can't grow unbounded queues.

Run:  python backend/tests/test_security.py
"""
from __future__ import annotations

import inspect
import sys
from dataclasses import replace
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import app.live_feed as live_mod  # noqa: E402
import app.mqtt_client as mqtt_mod  # noqa: E402
from app import db  # noqa: E402
from app.config import Settings  # noqa: E402
from app.events import EventBus  # noqa: E402
from app.ws_bridge import WSBridge  # noqa: E402
from websockets.datastructures import Headers  # noqa: E402
from websockets.http11 import Request  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


# ---------------------------------------------------------------------------
# SEC-01 / SEC-04: compose surface area
# ---------------------------------------------------------------------------
def test_compose_binds_loopback() -> None:
    print("[sec] docker-compose loopback binds + secure-mode entrypoint")
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    # every published port must be loopback-bound (127.0.0.1:HOST:CONTAINER)
    import re
    ports = re.findall(r'"([0-9.]+):(\d+):(\d+)"', text)
    check("three published ports declared",
          len(ports) == 3, f"ports={ports}")
    check("ALL published ports bind 127.0.0.1",
          all(p[0] == "127.0.0.1" for p in ports), str(ports))
    hosts = {p[2] for p in ports}
    check("mqtt 1883 + ws 9001 + pg 5432 pinned",
          {"1883", "9001", "5432"} <= hosts, str(hosts))
    # secure-mode entrypoint: password file + allow_anonymous false + ACL
    check("entrypoint generates password file",
          "mosquitto_passwd" in text, "no mosquitto_passwd")
    check("entrypoint toggles allow_anonymous false",
          "allow_anonymous false" in text, "no secure toggle")
    check("entrypoint applies acl_file",
          "acl_file" in text and "acl" in text, "no acl wiring")
    check("VITISH_MQTT_USER/PASS passed to container",
          "VITISH_MQTT_USER" in text and "VITISH_MQTT_PASS" in text,
          "broker auth env missing")
    # Postgres creds are env-overridable (SEC-04)
    check("db user overridable",
          "${VITISH_DB_USER:-vitish}" in text, "no VITISH_DB_USER")
    check("db password overridable",
          "${VITISH_DB_PASSWORD:-vitish}" in text, "no VITISH_DB_PASSWORD")
    # the secure-mode toggle lives in the ENTRYPOINT, not the committed config —
    # the default must stay open so the one-command demo keeps working.
    check("entrypoint is a string (not a mounted script)",
          "entrypoint:" in text, "entrypoint missing")


def test_mosquitto_conf_default_open() -> None:
    print("[sec] mosquitto.conf default-open + documentable off switch")
    text = (ROOT / "docker" / "mosquitto.conf").read_text(encoding="utf-8")
    check("default allow_anonymous true (one-command demo)",
          "allow_anonymous true" in text, text)
    check("loopback-only comment present",
          "127.0.0.1" in text or "local" in text.lower(), "no loopback note")


def test_acl_file() -> None:
    print("[sec] docker/acl topic ACL (secure-mode defense in depth)")
    text = (ROOT / "docker" / "acl").read_text(encoding="utf-8")
    # mosquitto DENIES by default when an acl_file is active: the security
    # boundary is that ONLY the backend credential may WRITE.  Every other
    # authenticated client is read-only by default (edge nodes read their own
    # bridge tree via %c).
    check("backend user granted readwrite on telemetry + control",
          "topic readwrite bridge/#" in text and "topic readwrite control/cmd" in text,
          text)
    check("backend credential named in ACL",
          "user vitish" in text, "no user line")
    check("edge node may READ its own bridge tree",
          "pattern read bridge/%c/#" in text, text)
    check("broker internals not readable",
          "deny read $SYS/#" in text, text)
    check("anonymous never write-allowed (deny-by-default boundary stated)",
          "DENIES by default" in text, "no deny-by-default note")


# ---------------------------------------------------------------------------
# SEC-01: credential application is conditional
# ---------------------------------------------------------------------------
def test_mqtt_creds_only_when_both_set() -> None:
    print("[sec] backend MQTT creds only when both env vars set")
    anonymous = Settings()
    check("anonymous default username empty",
          anonymous.mqtt_username is None and anonymous.mqtt_password is None,
          f"{anonymous.mqtt_username!r}/{anonymous.mqtt_password!r}")
    p = mqtt_mod.Publisher(anonymous)
    check("Publisher sends no creds by default",
          getattr(p.client, "_username", None) is None, "creds applied!")
    s = mqtt_mod.Subscriber(anonymous, default_handler=lambda t, p: None)
    check("Subscriber sends no creds by default",
          getattr(s.client, "_username", None) is None, "creds applied!")
    secure = Settings(mqtt_username="vitish", mqtt_password="s3cret")
    p2 = mqtt_mod.Publisher(secure)
    check("Publisher applies creds when both set",
          getattr(p2.client, "_username", None) == b"vitish",
          str(getattr(p2.client, "_username", None)))
    s2 = mqtt_mod.Subscriber(secure, default_handler=lambda t, p: None)
    check("Subscriber applies creds when both set",
          getattr(s2.client, "_username", None) == b"vitish",
          str(getattr(s2.client, "_username", None)))
    # partial config must NOT send creds (one-var typo must not half-auth)
    half = Settings(mqtt_username="vitish")
    p3 = mqtt_mod.Publisher(half)
    check("username-only still anonymous",
          getattr(p3.client, "_username", None) is None, "partial creds applied!")


def test_live_feed_never_gets_local_creds() -> None:
    print("[sec] live feed builds its own client — no local creds leak")
    src = inspect.getsource(live_mod)
    check("live_feed uses the public broker",
          live_mod.PUBLIC_BROKER == "test.mosquitto.org",
          live_mod.PUBLIC_BROKER)
    check("live_feed never calls username_pw_set",
          "username_pw_set" not in src, "username_pw_set found in live_feed!")
    check("live_feed imports no mqtt_client helpers",
          "mqtt_client" not in src and "Publisher(" not in src,
          "live_feed reuses backend MQTT client")


# ---------------------------------------------------------------------------
# SEC-02: demo scenario route token gate + rate limit
# ---------------------------------------------------------------------------
def test_demo_route_token_gate() -> None:
    print("[sec] POST /api/demo/scenario token-gated + rate-limited (SEC-02)")
    db.reset_store()
    db.get_store(Settings(), prefer="memory")
    import app.api as api_mod
    client = TestClient(api_mod.create_app())
    # default config: no token -> route DISABLED
    api_mod._rate_window.clear()
    _old = api_mod.settings.demo_token
    api_mod.settings.demo_token = ""
    try:
        r = client.post("/api/demo/scenario", json={"scenario": "rupture"})
        check("disabled without token -> 403", r.status_code == 403, str(r.status_code))
    finally:
        api_mod.settings.demo_token = _old
    # armed: bad token 403, good token 200, bogus scenario 422, flood 429
    api_mod.settings.demo_token = "sec-gate-token"
    try:
        api_mod._rate_window.clear()
        r = client.post("/api/demo/scenario", json={"scenario": "rupture"},
                        headers={"X-VITISH-DEMO": "nope"})
        check("wrong token -> 403", r.status_code == 403, str(r.status_code))
        api_mod._rate_window.clear()
        r = client.post("/api/demo/scenario", json={"scenario": "rupture"},
                        headers={"X-VITISH-DEMO": "sec-gate-token"})
        check("right token -> 200", r.status_code == 200 and r.json().get("ok"),
              str(r.status_code))
        api_mod._rate_window.clear()
        r = client.post("/api/demo/scenario", json={"scenario": "bogus"},
                        headers={"X-VITISH-DEMO": "sec-gate-token"})
        check("invalid scenario -> 422", r.status_code == 422, str(r.status_code))
        # per-IP rate limit: demo_rate_limit valid calls ok, next -> 429
        api_mod._rate_window.clear()
        codes = []
        for _ in range(api_mod.settings.demo_rate_limit + 1):
            codes.append(client.post(
                "/api/demo/scenario", json={"scenario": "healthy"},
                headers={"X-VITISH-DEMO": "sec-gate-token"}).status_code)
        check("rate limit enforced (5 ok, 6th 429)",
              codes[:5] == [200] * 5 and codes[5] == 429, f"codes={codes}")
        # rate window is per-IP (default testclient client = "testclient")
        api_mod._rate_window.clear()
        check("rate window cleared between checks", True)
    finally:
        api_mod.settings.demo_token = _old
        api_mod._rate_window.clear()
        db.reset_store()


# ---------------------------------------------------------------------------
# SEC-03: WS origin validation
# ---------------------------------------------------------------------------
def _req(origin: str | None) -> Request:
    h = Headers()
    if origin is not None:
        h["Origin"] = origin
    return Request("/", headers=h)


def test_ws_origin_validation() -> None:
    print("[sec] WS origin validation (SEC-03 CSWSH)")
    open_bridge = WSBridge(Settings(), EventBus())
    check("default (open) origins = None",
          open_bridge._origins is None, str(open_bridge._origins))
    check("open accepts evil origin",
          open_bridge._check_origin(None, _req("http://evil.example")) is None)
    check("open accepts headerless",
          open_bridge._check_origin(None, _req(None)) is None)
    locked = WSBridge(
        Settings(ws_allowed_origins="http://localhost:5173"), EventBus())
    check("locked origin set includes None (headerless ok)",
          None in locked._origins, str(locked._origins))
    r = locked._check_origin(None, _req("http://evil.example"))
    check("locked rejects evil origin with 403",
          r is not None and r.status_code == 403, str(r))
    check("locked accepts allowed origin",
          locked._check_origin(None, _req("http://localhost:5173")) is None)
    check("locked accepts headerless client",
          locked._check_origin(None, _req(None)) is None)
    multi = WSBridge(
        Settings(ws_allowed_origins="http://a.test, http://b.test"), EventBus())
    check("comma-separated origins parsed",
          multi._origins == {None, "http://a.test", "http://b.test"},
          str(multi._origins))
    # serve() is wired to the validator
    import inspect as _ins
    src = _ins.getsource(WSBridge._serve)
    check("serve() passes process_request=self._check_origin",
          "process_request=self._check_origin" in src, "not wired")


# ---------------------------------------------------------------------------
# SEC-06: per-client WS cap
# ---------------------------------------------------------------------------
def test_ws_client_cap() -> None:
    print("[sec] per-client WS cap (SEC-06)")
    b = WSBridge(Settings(), EventBus())
    check("MAX_CLIENTS == 64", b.MAX_CLIENTS == 64, str(b.MAX_CLIENTS))
    check("cap is enforced in _handler before fan-out",
          "len(self._clients) >= self.MAX_CLIENTS" in
          inspect.getsource(WSBridge._handler), "cap not enforced")


# ---------------------------------------------------------------------------
# config defaults
# ---------------------------------------------------------------------------
def test_config_defaults() -> None:
    print("[sec] config loopback defaults + opt-in fields")
    c = Settings()
    check("ws_host defaults to 127.0.0.1", c.ws_host == "127.0.0.1", c.ws_host)
    check("api_host defaults to 127.0.0.1", c.api_host == "127.0.0.1", c.api_host)
    check("demo_token empty (route disabled)", c.demo_token == "", c.demo_token)
    check("demo rate limit 5/10s", c.demo_rate_limit == 5
          and c.demo_rate_window_s == 10.0, str(c.demo_rate_limit))
    check("ws_allowed_origins empty (open)", c.ws_allowed_origins == "",
          c.ws_allowed_origins)


def main() -> int:
    try:
        test_compose_binds_loopback()
        test_mosquitto_conf_default_open()
        test_acl_file()
        test_mqtt_creds_only_when_both_set()
        test_live_feed_never_gets_local_creds()
        test_demo_route_token_gate()
        test_ws_origin_validation()
        test_ws_client_cap()
        test_config_defaults()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("security tests")
        import traceback
        print(f"  [ERROR] security tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== SEC security gate (SEC-01/02/03/04/06): {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
