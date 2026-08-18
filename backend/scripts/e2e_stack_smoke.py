"""Item 12 · twin+backend e2e stack smoke on the real event bus.

Boots the one-command stack (`app/run_all.py`, NO --demo/--live) as a child
process — the exact same default path CI runs — then proves the twin's data
contracts end-to-end over loopback:

    HTTP  /health         service up (service == vitish-shm-backend, bridge z24)
    HTTP  /api/bridges    all bridges present (count == 50, hero id == z24)
    HTTP  /api/config     z24 bridge block + BHI weights block (ENH-10 contract)
    WS    one connect     hello frame, then a live bridge/z24/bhi envelope with
                          a numeric bhi and a valid state — the exact frame the
                          twin's BhiPanel renders.

Everything runs over loopback.  The simulator streams real Z24 replay when
data/z24/inputs.npy is present and falls back to synthetic pink-noise
otherwise (never depends on the 992 MB download), so this smoke is
deterministic in CI without the dataset.  Determinism guard: the site
TEMP probe (Open-Meteo) is forced into its offline modeled fallback via
VITISH_SITE_TEMP_DISABLE=1, mirroring scripts/run_tests.sh.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets.sync.client  # noqa: F401  (websockets >= 12 sync client)

BACKEND = str(Path(__file__).resolve().parents[1])
BRIDGE_THEME = "z24"
VALID_STATES = {"GREEN", "AMBER", "RED"}

# banner lines carry annotations ("(twin data path)") after the port
_WS_PORT_RE = re.compile(r"ws://[^:]+:(\d+)")

PASS = 0
FAIL = 0


def _check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {label}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f"  ({detail})" if detail else ""))


def _http(url: str, timeout: float = 3.0):
    """GET a URL; return (status, json) or (None, None) on any failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        return None, exc


def _wait_http(url: str, deadline: float):
    while time.time() < deadline:
        status, body = _http(url)
        if status is not None:
            return status, body
        time.sleep(0.3)
    return None, None


def main() -> int:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")                    # Windows σ/± banner text
    env["VITISH_SITE_TEMP_DISABLE"] = "1"                # offline modeled fallback
    proc = subprocess.Popen(
        [sys.executable, "-u", "app/run_all.py"],
        cwd=BACKEND, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", env=env,
    )

    api_port = None
    ws_port = None
    banner_lines: list[str] = []
    try:
        # --- boot + parse the banner for the real (possibly fallback) ports ------
        deadline = time.time() + 30
        while time.time() < deadline and proc.poll() is None:
            line = proc.stdout.readline()
            if line:
                banner_lines.append(line.rstrip())
                if "WebSocket twin" in line:
                    m = _WS_PORT_RE.search(line)
                    if m:
                        ws_port = m.group(1)
                if "REST API" in line:
                    api_port = line.strip().split(":")[-1].strip()
                if "Data source" in line:
                    print("DATA SOURCE:", line.strip().split(":", 1)[1].strip())
            if api_port and ws_port:
                break
            time.sleep(0.05)

        if not (api_port and ws_port):
            print("\n".join(banner_lines[-15:]))
            _check("banner exposes REST + WS ports", False,
                   f"api_port={api_port} ws_port={ws_port}")
            return 1
        print(f"PORTS: api={api_port} ws={ws_port}")

        api_base = f"http://127.0.0.1:{api_port}"
        ws_url = f"ws://127.0.0.1:{ws_port}"
        http_deadline = time.time() + 25

        # --- /health -------------------------------------------------------------
        status, body = _wait_http(f"{api_base}/health", http_deadline)
        _check("GET /health responds 200", status == 200, f"status={status}")
        health = body if isinstance(body, dict) else {}
        _check("health.status == ok", health.get("status") == "ok",
               f"status={health.get('status')}")
        _check("health.service == vitish-shm-backend",
               health.get("service") == "vitish-shm-backend",
               f"service={health.get('service')}")
        _check("health.bridge == z24", health.get("bridge") == BRIDGE_THEME,
               f"bridge={health.get('bridge')}")

        # --- /api/bridges --------------------------------------------------------
        status, body = _wait_http(f"{api_base}/api/bridges", http_deadline)
        _check("GET /api/bridges responds 200", status == 200, f"status={status}")
        bridges = body.get("bridges") if isinstance(body, dict) else []
        _check("api/bridges.count == 50", body.get("count") == 50,
               f"count={body.get('count')}")
        _check("api/bridges hero is z24",
               isinstance(body, dict) and body.get("hero", {}).get("id") == BRIDGE_THEME,
               f"hero_id={body.get('hero', {}).get('id')}")
        _check("api/bridges list length == 50", len(bridges) == 50,
               f"len={len(bridges)}")

        # --- /api/config ---------------------------------------------------------
        status, body = _wait_http(f"{api_base}/api/config", http_deadline)
        _check("GET /api/config responds 200", status == 200, f"status={status}")
        config = body if isinstance(body, dict) else {}
        _check("api/config.bridge == z24",
               config.get("bridge") == BRIDGE_THEME,
               f"bridge={config.get('bridge')}")
        bhi = config.get("bhi", {})
        _check("api/config.bhi.weights present (ENH-10)",
               isinstance(bhi.get("weights"), dict) and len(bhi["weights"]) == 3,
               f"weights={bhi.get('weights')}")
        _check("api/config.ws_port matches banner",
               str(config.get("ws_port")) == str(ws_port),
               f"config={config.get('ws_port')} banner={ws_port}")

        # --- one WS connect: hello, then a live bridge/z24/bhi frame -------------
        ws_ok = False
        hello_seen = False
        got_topic = None
        got_state = None
        got_bhi = None
        topic = f"bridge/{BRIDGE_THEME}/bhi"
        # PERF-09: a loaded CI box can stall the sim thread (torch detector
        # prebuilds + parallel suite) so the FIRST scored BHI legitimately lands
        # tens of seconds after connect — hello arrives on the WS thread the
        # instant the socket opens.  Budget generously for the first frame.
        ws_deadline = time.time() + 60
        try:
            with websockets.sync.client.connect(ws_url, open_timeout=10.0) as conn:
                while time.time() < ws_deadline:
                    try:
                        frame = json.loads(conn.recv(timeout=5.0))
                    except TimeoutError:
                        continue
                    t = frame.get("topic", "")
                    if t == "hello":
                        hello_seen = True
                        continue
                    if t == topic:
                        try:
                            bhi_val = float(frame.get("bhi"))
                        except (TypeError, ValueError):
                            continue
                        state = frame.get("state")
                        if state in VALID_STATES:
                            got_topic, got_state, got_bhi = t, state, bhi_val
                            ws_ok = True
                            break
        except Exception as exc:
            print("  WS ERR:", exc)
        _check("WS connect -> hello frame", hello_seen)
        _check(f"WS live {topic} with valid state arrives",
               ws_ok, f"state={got_state} bhi={got_bhi}")
        print(f"  WS FRAME: topic={got_topic} state={got_state} bhi={got_bhi}")

        print("BANNER (tail):")
        for ln in banner_lines[-8:]:
            print("  |", ln)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        try:
            proc.stdout.close()
        except Exception:
            pass

    ok = FAIL == 0
    print(f"E2E STACK SMOKE: {'PASS' if ok else 'FAIL'} ({PASS} pass, {FAIL} fail)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())