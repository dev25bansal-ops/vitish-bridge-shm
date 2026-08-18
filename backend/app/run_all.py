"""
VITISH 2026 · PS#99 SHM — one-command backend stack.

    python app/run_all.py           simulator + WS bridge + FastAPI
    python app/run_all.py --demo    ... + storyboard demo driver

Everything runs in one process (threads) so the simulator, MQTT subscriber,
fusion service, persistence recorder, WebSocket bridge, API and (optionally)
the demo driver share a single event bus and store.  The honest data path is
simulator -> MQTT -> subscriber -> bus -> WebSocket/API; when the broker is
unreachable the simulator/fusion fall back to streaming directly on the bus so
the demo never depends on Docker.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# launch bootstrap (works from repo root or backend/)
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, setup_logging, settings  # noqa: E402
from app import bridge_registry  # noqa: E402
from app import api as api_mod  # noqa: E402
from app import db  # noqa: E402
from app import events  # noqa: E402
from app import simulator as sim_mod  # noqa: E402
from app import ws_bridge as ws_mod  # noqa: E402
from app import demo_driver as drv_mod  # noqa: E402
from app import fusion as fusion_mod  # noqa: E402
from app import stiffness as stiffness_mod  # noqa: E402
from app import mqtt_client  # noqa: E402
from app import live_feed as live_mod  # noqa: E402
from app import edge_node as edge_mod  # noqa: E402
from app import telegram_alerts as tg_mod  # noqa: E402

log = logging.getLogger("run_all")


def _banner(cfg: Settings, store, sim: sim_mod.Simulator, demo: bool,
            api_port: int, ws_port: int, live: bool = False,
            live_feed=None) -> None:
    line = "=" * 64
    print(line)
    print(" VITISH 2026 · PS#99 SHM — backend stack")
    print("-" * 64)
    print(f" MQTT broker     : mqtt://{cfg.broker_host}:{cfg.broker_port}")
    print(f" WebSocket twin  : ws://localhost:{ws_port}      (twin data path)")
    print(f" REST API        : http://localhost:{api_port}")
    print(f"    /health")
    print(f"    /api/bridges")
    print(f"    /api/bridges/geojson")
    print(f"    /api/live              (live MQTT feed status — with --live)")
    print(f"    /api/manifest           (D1-5 data-realism manifest)")
    print(f"    /api/bridge/{cfg.bridge_id}/history?metric=bhi|rms")
    print(f"    /api/bridge/{cfg.bridge_id}/alerts?limit=N")
    print(f"    /api/bridge/{cfg.bridge_id}/state")
    print(f"    POST /api/demo/scenario  {{\"scenario\": \"healthy|rupture\"}}")
    print(f" Persistence     : {getattr(store, 'source', 'postgres')}")
    print(f" Data source     : {sim.data_source}")
    if live and live_feed is not None:
        st = live_feed.status()
        live_status = (f"{st['broker']} {'CONNECTED' if st['connected'] else 'waiting'} "
                       f"({st['received']} rx / {st['published']} pub)")
    else:
        live_status = ""
    print(f" Live MQTT feed  : {'ENABLED (' + live_status + ')' if live else 'disabled (--live)'}")
    edge_st = edge_mod.get_edge_status()
    if edge_st is not None:
        et = "ONLINE" if edge_st["online"] else "waiting for node"
        edge_ids = ",".join(edge_mod.EDGE_BRIDGES)
        print(f" Edge node       : bridge={edge_ids} primary={edge_mod.EDGE_BRIDGE} "
              f"{et} ({edge_st['received']} rx)  [real {edge_st['hardware']}]")
    tg_st = tg_mod.get_status()
    if tg_st is not None and tg_st["enabled"]:
        print(f" Telegram alerts : ENABLED (chat {tg_st['chat']}, "
              f"min={tg_st['min_severity']}, {tg_st['throttle_s']:.0f}s throttle)")
    print(f" Demo driver     : {'ENABLED (speed %.2fx)' % settings.demo_speed if demo else 'disabled'}")
    print(line, flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="VITISH SHM backend stack")
    parser.add_argument("--demo", action="store_true", help="start the demo driver")
    parser.add_argument("--scenario", choices=["healthy", "rupture"], default="healthy")
    parser.add_argument("--synthetic", action="store_true", help="force synthetic stream")
    parser.add_argument("--rate", type=float, default=1.0, help="simulator speed")
    parser.add_argument("--speed", type=float, default=1.0, help="demo driver speed")
    parser.add_argument("--loops", type=int, default=0, help="simulator 60s segments")
    parser.add_argument("--live", action="store_true",
                        help="ingest live public-broker MQTT as bridge='live-demo' "
                             "(also honored via VITISH_LIVE=1)")
    args = parser.parse_args(argv)

    setup_logging()
    cfg = settings
    cfg.demo_speed = args.speed
    bus = events.get_bus()

    # --- PERF-01: eager trained-detector prebuild ---------------------------------
    # The first trained_push used to build the detector inline (torch.load +
    # joblib, measured ~2.1s on CUDA) — a stall that hit the first anomaly push.
    # Kick the build off on a background daemon thread NOW, before the simulator
    # starts streaming; trained_push never blocks on it (non-blocking lock, the
    # deterministic floor carries any window scored before the build lands).
    # Fire-and-forget: a missing/broken artifact degrades to push=0, never a crash.
    try:
        from models.vibration import demo_predictor as dp_mod
        dp_mod.prebuild_detector()
    except Exception as exc:  # pragma: no cover - models/ import must never break boot
        log.debug("trained-detector prebuild skipped (%s)", exc)

    # --- PERF-03: eager crack-model prebuild --------------------------------------
    # The t=45 cv beat used to pay a ~4.7s torch.load of crack_seg.pt inline on
    # the scoring thread.  Kick off the same background build now so the model is
    # warm before the first cv beat; cv_feed.get_detector() is non-blocking and
    # degrades to the tagged scripted fallback if it is still loading.  Also
    # warms any CUDA context before the demo's first cv beat.
    try:
        from app import cv_feed as cv_mod
        cv_mod.prebuild_detector()
    except Exception as exc:  # pragma: no cover
        log.debug("cv-detector prebuild skipped (%s)", exc)

    # --- optional live public-broker feed (opt-in, fail-soft) -----------------
    live = args.live or os.environ.get("VITISH_LIVE") == "1"
    live_feed = None
    live_recorder_token = None

    # --- shared services ------------------------------------------------------
    publisher = mqtt_client.Publisher(cfg)
    publisher.start()

    store = db.get_store(cfg)

    subscriber = mqtt_client.Subscriber(
        cfg, default_handler=mqtt_client.make_mqtt_router(bus))
    subscriber.start()

    fusion = fusion_mod.FusionService(cfg, bus, store, publisher)
    fusion.start()

    stiffness_tracker = stiffness_mod.StiffnessTracker(cfg, bus)
    stiffness_mod.set_tracker(stiffness_tracker)
    stiffness_tracker.start()

    recorder_token = db.attach_recorder(cfg, bus, store)

    # --- item 14: env-registered extra bridges (bridge registry) ---------------
    # Each extra is recorded under its OWN bridge id (same per-bridge routing as
    # the edge nodes below), so /api/bridge/<extra>/history + /state serve real
    # fused rows instead of a placeholder when extras are configured.
    extra_recorder_tokens = [
        db.attach_recorder(cfg, bus, store, pattern=f"bridge/{b}/#")
        for b in bridge_registry.extra_bridge_ids()
    ]

    # --- real edge nodes (edge slots: esp32-1 + esp01-1 by default) ------------
    # Always-on: cheap bus subscribers; show OFFLINE until a board streams.
    # Every edge slot gets a recorder so a stock-flashed ESP-01S (esp01-1) is
    # NOT silently ignored (S8 fix) — rows are tagged with the topic's bridge id.
    edge = edge_mod.EdgeNodeMonitor(bus)
    edge_mod.set_edge_monitor(edge)
    edge.start()
    edge_recorder_tokens = [
        db.attach_recorder(cfg, bus, store, pattern=f"bridge/{b}/#")
        for b in edge_mod.EDGE_BRIDGES
    ]
    log.info("edge node monitor ENABLED — bridges=%s (real hardware)",
             ",".join(edge_mod.EDGE_BRIDGES))

    # --- out-of-band alert dispatch (Telegram, NEW-01) --------------------------
    # Optional + fail-open: enabled only when VITISH_TELEGRAM_TOKEN and
    # VITISH_TELEGRAM_CHAT are set.  In --demo the footer honestly labels the
    # ping as the simulated story arc, never real bridge telemetry.
    tg_disp = None
    if tg_mod.TelegramAlertDispatcher(bus).enabled:
        footer = ("— VITISH SHM · SIMULATED PS#99 demo pipeline — this is the "
                  "storyboard arc, not real bridge telemetry" if args.demo
                  else "— VITISH SHM alert dispatcher")
        tg_disp = tg_mod.TelegramAlertDispatcher(
            bus, footer=footer)
        tg_mod.set_dispatcher(tg_disp)
        tg_disp.start()

    if live:
        live_feed = live_mod.LiveFeed(bus)
        live_mod.set_live_feed(live_feed)
        live_feed.start()
        # persist live accel rows too, tagged bridge='live-demo' (source tag in
        # the payload is the honest provenance marker; never fused into z24 BHI)
        # Persistence decision (ROADMAP line 91): the /telemetry envelopes are
        # deliberately NOT persisted — public-broker values are unvetted
        # third-party scalars, and the thin /accel rows already prove ingestion;
        # nothing consumes stored live telemetry today. The WS bridge likewise
        # does NOT forward bridge/live-demo/# (the twin reads live status via
        # REST /api/live).
        live_recorder_token = db.attach_recorder(cfg, bus, store,
                                                 pattern="bridge/live-demo/#")
        log.info("live feed ENABLED — bridge='live-demo' source='public-mosquitto'")
    else:
        live_mod.set_live_feed(None)

    ws = ws_mod.WSBridge(cfg, bus, scenario=args.scenario, store=store)
    ws_mod.set_current_bridge(ws)
    ws.start()
    ws_port = cfg.ws_port
    for _ in range(40):  # wait for the ws bridge to bind (may fall back to a free port)
        if getattr(ws, "bound_port", None) is not None:
            ws_port = ws.bound_port
            break
        time.sleep(0.05)

    # --- API in a thread --------------------------------------------------------
    api_server, api_port = _run_api(cfg)
    if api_server is None:
        log.error("could not start API")
        return 1

    sim = sim_mod.Simulator(cfg, publisher, bus=bus, synthetic=args.synthetic,
                            scenario=args.scenario, loops=args.loops, rate=args.rate)
    sim_mod.set_simulator(sim)   # D2-12: API reads the seeded-defect narrative

    driver = None
    if args.demo:
        driver = drv_mod.DemoDriver(cfg, bus, publisher, timeline="demo",
                                    speed=args.speed)

    _banner(cfg, store, sim, demo=args.demo, api_port=api_port, ws_port=ws_port,
            live=live, live_feed=live_feed)

    sim_thread = threading.Thread(target=sim.run, name="simulator", daemon=True)
    sim_thread.start()
    driver_thread = None
    if driver is not None:
        driver_thread = threading.Thread(target=driver.run, name="demo-driver", daemon=True)
        driver_thread.start()

    # --- run until Ctrl-C -------------------------------------------------------
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nshutting down backend stack...")
    finally:
        _shutdown(sim, driver, api_server, ws, fusion, subscriber, publisher,
                  bus, recorder_token, live_feed, live_recorder_token,
                  edge_recorder_token, extra_recorder_tokens, edge, tg_disp)
    return 0


def _probe_port(host: str, port: int, timeout: float = 0.4) -> bool:
    """True when nothing is accepting connections on host:port (port is free)."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return False
    except OSError:
        return True


def _find_free_port(host: str, start: int, attempts: int = 20) -> Optional[int]:
    for port in range(start, start + attempts):
        if _probe_port(host, port):
            return port
    return None


def _run_api(cfg: Settings):
    import uvicorn
    host = cfg.api_host
    port = cfg.api_port
    # Probe/find on loopback even when binding on 0.0.0.0: a local listener
    # (0.0.0.0:8000 included) is always reachable via 127.0.0.1, whereas a
    # connect() to 0.0.0.0 as a *destination* silently reports "free" on
    # Windows — which used to send us straight into an EADDRINUSE bind failure
    # (ROADMAP line 90: e2e then polled a stale backend on the claimed port).
    probe_host = "127.0.0.1"
    if not _probe_port(probe_host, port):
        alt = _find_free_port(probe_host, port + 1)
        if alt is None:
            log.error("API: no free port near %d", port)
            return None, None
        log.warning("API: port %d busy — using %d instead", port, alt)
        port = alt
    try:
        app = api_mod.create_app()
        server = uvicorn.Server(uvicorn.Config(
            app, host=host, port=port, log_level="warning"))
        t = threading.Thread(target=server.run, name="api-uvicorn", daemon=True)
        t.start()
        # wait until the server is actually serving
        for _ in range(100):
            if server.started:
                api_mod.set_api_port(port)
                return server, port
            time.sleep(0.05)
        # bind failed (e.g. port raced away after the probe); returning a
        # "server" here let the banner claim a port that serves nothing
        log.error("API failed to bind %s:%d — server did not start", host, port)
        return None, None
    except Exception as exc:
        log.exception("API failed to start: %s", exc)
        return None, None


def _shutdown(sim, driver, api_server, ws, fusion, subscriber, publisher, bus,
              recorder_token, live_feed=None, live_recorder_token=None,
              edge_recorder_token=None, extra_recorder_tokens=None,
              edge=None, tg=None) -> None:
    sim.stop()
    if driver is not None:
        driver.stop()
    ws.stop()
    fusion.stop()
    tracker = stiffness_mod.get_tracker()
    if tracker is not None:
        tracker.stop()
    bus.unsubscribe(recorder_token)
    if live_recorder_token is not None:
        bus.unsubscribe(live_recorder_token)
    if edge_recorder_token:
        # edge_recorder_token is a list (one recorder per edge bridge id)
        for tok in edge_recorder_token:
            bus.unsubscribe(tok)
    if extra_recorder_tokens:
        # item 14: one recorder subnet per env-registered extra bridge
        for tok in extra_recorder_tokens:
            bus.unsubscribe(tok)
    if edge is not None:
        edge.stop()
    if tg is not None:
        tg_mod.set_dispatcher(None)
        tg.stop()
    if live_feed is not None:
        live_feed.stop()
    subscriber.stop()
    publisher.stop()
    if api_server is not None:
        api_server.should_exit = True
    log.info("backend stack stopped")


if __name__ == "__main__":
    sys.exit(main())
