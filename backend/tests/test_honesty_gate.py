"""
VITISH 2026 · PS#99 SHM — item 15: honesty-label regression gate.

Run from backend/:  python tests/test_honesty_gate.py

This is the REGRESSION GATE for the honesty posture: it sweeps every
human-facing API surface and asserts the simulated / fallback / illustrative
labels are ALWAYS present, and that the LIVE badge is GATED on a real measured
packet rather than a slot/stream being monitored.  If a future change drops a
label or lets a non-live surface claim "live", this test fails.

Gate invariants, by section:

  [1] LIVE-badge gating — nothing claims live until a real packet is measured:
        * an edge node slot with NO measured packet  -> live=False + live_label
          saying why (firmware committed, not flashed/bench-tested)
        * the same slot AFTER a real packet          -> live=True, but the accel
          is still the honest self-test BIST signal (never real vibration)
        * the hero is live-as-stream, and its telemetry block says the signal
          is a replay/synthetic model — never a live field sensor
        * /api/live is not "enabled" unless the stack was started with --live

  [2] simulated/fallback labels always present:
        * /api/manifest  data_source + data_source_label + honesty.note +
          live_public_feed.note + edge_node.note + site_temperature.source_label
          (both the measured AND the modeled fallback wording, via injection)
        * /api/config    multi_bridge.onboard_label + bhi block
        * /api/bridges   per-class labels (hero / regulators / extras)
        * hero /state    telemetry.label
        * regulator /state  illustrative + note
        * extra /state   synthetic + source_label (when VITISH_EXTRA_BRIDGES set)
        * /api/fleet/priority  priors_label + note (never a certified RUL)
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import bridge_registry, channel_models as cm  # noqa: E402
from app import contract, db, edge_node as edge_mod  # noqa: E402
from app import site_temperature as site_temp_mod  # noqa: E402
from app.config import settings  # noqa: E402
from app.events import get_bus  # noqa: E402

# Deterministic, air-gapped: force the offline site-temperature fallback so the
# modeled label is what the manifest serves (the fallback label invariant).
site_temp_mod.set_network_disabled(True)

# Start in the DEFAULT (no extras) state regardless of the runner's env.
_ENV = bridge_registry.ENV_VAR
_SAVED_ENV = os.environ.get(_ENV)
os.environ.pop(_ENV, None)

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, info=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok: {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}  {info}")
        print(f"FAIL: {name}  {info}")


def _accel(bridge: str, fw: str) -> dict:
    """Contract-shaped edge accel payload (self-test BIST tone)."""
    return {"bridge": bridge, "node": 1, "fs": 100, "ts": contract.now(),
            "rms": 0.02, "flag": 0, "signal_kind": "self-test-bist",
            "rssi": -55, "heap": 201120, "uptime_s": 42.0, "fw": fw,
            "samples": [0.0] * 100}


def _client():
    from fastapi.testclient import TestClient
    from app.api import create_app
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# [1] LIVE-badge gating
# ---------------------------------------------------------------------------
def test_live_badge_gating() -> None:
    print("[1] LIVE-badge gating — nothing claims live before a real packet")
    bus = get_bus()
    mon = edge_mod.EdgeNodeMonitor(bus)
    mon.start()
    edge_mod.set_edge_monitor(mon)
    db.reset_store()
    client = _client()
    try:
        # --- edge slot, no measured packet yet -------------------------------
        r = client.get("/api/bridge/esp32-1/state")
        check("edge state 200", r.status_code == 200)
        js = r.json()
        check("edge NOT live before a packet (LIVE gating)",
              js["live"] is False, f"live={js['live']!r}")
        check("edge off-line label says why",
              "OFF-LINE" in js.get("live_label", "") or
              "not flashed" in js.get("live_label", ""),
              f"live_label={js.get('live_label')!r}")
        check("edge honesty block present",
              "no accelerometer" in js.get("honesty", {}).get("accel_is", ""))

        # --- after a real packet (monitor online) ----------------------------
        bus.publish("bridge/esp32-1/accel", _accel("esp32-1", "vitish-edge-esp32-0.1"),
                    source="test")
        time.sleep(0.05)
        r = client.get("/api/bridge/esp32-1/state")
        js = r.json()
        check("edge live AFTER a measured packet", js["live"] is True,
              f"live={js['live']!r}")
        check("edge online after packet", js["online"] is True)
        check("edge accel still honest BIST (never real vibration)",
              js.get("signal_kind") == "self-test-bist" and
              "no accelerometer" in js.get("honesty", {}).get("accel_is", ""))

        # --- hero: live stream, but NOT a live field sensor ------------------
        r = client.get("/api/bridge/z24/state")
        js = r.json()
        check("hero state 200", r.status_code == 200)
        check("hero live flag is stream-liveness", js["live"] is True)
        tel = js.get("telemetry") or {}
        check("hero telemetry block present", bool(tel))
        check("hero telemetry source is honest (replay|synthetic)",
              tel.get("source") in ("z24-replay", "synthetic"),
              f"telemetry.source={tel.get('source')!r}")
        check("hero telemetry label non-empty",
              bool(tel.get("label")))
        check("hero telemetry note disambiguates (never a live field sensor)",
              "never a live field sensor" in tel.get("note", ""),
              f"note={tel.get('note')!r}")

        # --- /api/live disabled by default ------------------------------------
        r = client.get("/api/live")
        js = r.json()
        check("/api/live not enabled by default", js.get("enabled") is False)
        check("/api/live note points at --live", "--live" in js.get("note", ""))
    finally:
        edge_mod.set_edge_monitor(None)
        mon.stop()
        db.reset_store()


# ---------------------------------------------------------------------------
# [2] simulated/fallback labels always present
# ---------------------------------------------------------------------------
def test_simulated_and_fallback_labels() -> None:
    print("[2] simulated/fallback labels always present (default, no extras)")
    db.reset_store()
    client = _client()
    try:
        # --- /api/manifest -----------------------------------------------------
        r = client.get("/api/manifest")
        check("manifest 200", r.status_code == 200)
        m = r.json()
        check("manifest data_source honest value",
              m.get("data_source") in ("z24-replay", "synthetic", "live-demo"),
              f"data_source={m.get('data_source')!r}")
        check("manifest data_source_label non-empty", bool(m.get("data_source_label")))
        check("manifest honesty.note present",
              bool((m.get("honesty") or {}).get("note", "")))
        check("manifest live_public_feed.note present",
              bool((m.get("live_public_feed") or {}).get("note", "")) and
              "never fused" in (m.get("live_public_feed") or {}).get("note", ""))
        check("manifest edge_node.note present",
              bool((m.get("edge_node") or {}).get("note", "")) and
              "never fused" in (m.get("edge_node") or {}).get("note", ""))
        st = m.get("site_temperature") or {}
        check("manifest site_temperature block present", bool(st))
        check("site_temp source honest (measured|modeled)",
              st.get("source") in ("open-meteo", "synthetic"),
              f"source={st.get('source')!r}")
        check("site_temp source_label non-empty + honest wording",
              bool(st.get("source_label")) and
              ("Open-Meteo" in st.get("source_label", "") or
               "simulated seasonal" in st.get("source_label", "")),
              f"label={st.get('source_label')!r}")

        # --- /api/config -------------------------------------------------------
        r = client.get("/api/config")
        cfg = r.json()
        mb = cfg.get("multi_bridge") or {}
        check("config multi_bridge.block present", bool(mb))
        check("config onboarding label present + honest",
              "days" in mb.get("onboard_label", "") and
              "not a same-day plug-in" in mb.get("onboard_label", ""),
              f"label={mb.get('onboard_label')!r}")
        check("config bhi block present (contract parity)",
              isinstance(cfg.get("bhi", {}).get("weights"), dict))

        # --- /api/bridges (per-class labels) -----------------------------------
        r = client.get("/api/bridges")
        b = r.json()
        labels = b.get("labels") or {}
        check("bridges count 50 (no extras)", b.get("count") == 50,
              f"count={b.get('count')!r}")
        check("bridges labels.hero present",
              "never a live field sensor" in labels.get("hero", ""))
        check("bridges labels.regulators present",
              "never real inspection data" in labels.get("regulators", ""))
        check("bridges labels.extras None when no extras",
              labels.get("extras") is None, f"extras={labels.get('extras')!r}")

        # --- hero state telemetry ----------------------------------------------
        r = client.get("/api/bridge/z24/state")
        tel = (r.json() or {}).get("telemetry") or {}
        check("hero telemetry.label non-empty on state", bool(tel.get("label")))

        # --- regulator state is illustrative -----------------------------------
        r = client.get("/api/bridge/reg-01/state")
        rg = r.json()
        check("regulator state 200", r.status_code == 200)
        check("regulator state labeled illustrative",
              rg.get("illustrative") is True)
        check("regulator state note honest",
              "never real inspection data" in rg.get("note", ""),
              f"note={rg.get('note')!r}")
        check("regulator NOT live", rg.get("live") is False)

        # --- fleet/priority honest labels --------------------------------------
        r = client.get("/api/fleet/priority")
        fp = r.json()
        check("fleet/priority 200", r.status_code == 200)
        check("fleet/priority priors_label non-empty",
              bool(fp.get("priors_label", "")))
        check("fleet/priority note honest (not certified)",
              "not a certified RUL" in fp.get("note", ""),
              f"note={fp.get('note')!r}")

        # --- measured site-temp label path (injected) --------------------------
        print("    -- measured site-temp label path (injected, no network)")
        site_temp_mod.set_network_disabled(False)
        old_http = site_temp_mod._http_get
        site_temp_mod._http_get = (
            lambda url, timeout_s: b'{"current": {"temperature_2m": 21.5}}')
        try:
            st = site_temp_mod.probe_site_temp()
            check("measured source label present",
                  st.get("source") == "open-meteo" and
                  "measured air temperature" in st.get("source_label", ""),
                  f"source={st.get('source')!r} label={st.get('source_label')!r}")
        finally:
            site_temp_mod._http_get = old_http
            site_temp_mod.set_network_disabled(True)
    finally:
        db.reset_store()


def test_extras_carry_simulated_labels() -> None:
    print("[3] extras (VITISH_EXTRA_BRIDGES) carry the simulated label")
    db.reset_store()
    os.environ[_ENV] = "testbridge:Test Span:Testing:TS:30.1:75.2"
    client = _client()
    try:
        r = client.get("/api/bridges")
        b = r.json()
        check("bridges count 51 with one extra", b.get("count") == 51,
              f"count={b.get('count')!r}")
        check("bridges labels.extras present when extras exist",
              bridge_registry.SOURCE_LABEL in (b.get("labels") or {}).get("extras", ""))
        r = client.get("/api/bridge/testbridge/state")
        js = r.json()
        check("extra state 200", r.status_code == 200)
        check("extra state synthetic: True", js.get("synthetic") is True)
        check("extra state source_label present",
              "simulated telemetry" in js.get("source_label", ""),
              f"label={js.get('source_label')!r}")
        check("extra state onboard_label present",
              "days" in js.get("onboard_label", ""),
              f"label={js.get('onboard_label')!r}")
    finally:
        db.reset_store()
        if _SAVED_ENV is None:
            os.environ.pop(_ENV, None)
        else:
            os.environ[_ENV] = _SAVED_ENV


def main() -> int:
    test_live_badge_gating()
    test_simulated_and_fallback_labels()
    test_extras_carry_simulated_labels()
    print(f"\nhonesty-label gate: {PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILURES:")
        for f in FAILURES:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())