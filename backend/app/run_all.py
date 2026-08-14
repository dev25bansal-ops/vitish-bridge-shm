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

# launch bootstrap (works from repo root or backend/)
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, setup_logging, settings  # noqa: E402
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
    print(f"    /api/bridge/{cfg.bridge_id}/history?metric=bhi|rms")
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

    if live:
        live_feed = live_mod.LiveFeed(bus)
        live_mod.set_live_feed(live_feed)
        live_feed.start()
        # persist live accel rows too, tagged bridge='live-demo' (source tag in
        # the payload is the honest provenance marker; never fused into z24 BHI)
        live_recorder_token = db.attach_recorder(cfg, bus, store,
                                                 pattern="bridge/live-demo/#")
        log.info("live feed ENABLED — bridge='live-demo' source='public-mosquitto'")
    else:
        live_mod.set_live_feed(None)

    ws = ws_mod.WSBridge(cfg, bus, scenario=args.scenario)
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
                  bus, recorder_token, live_feed, live_recorder_token)
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
    if not _probe_port(host, port):
        alt = _find_free_port(host, port + 1)
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
                return server, port
            time.sleep(0.05)
        return server, port
    except Exception as exc:
        log.exception("API failed to start: %s", exc)
        return None, None


def _shutdown(sim, driver, api_server, ws, fusion, subscriber, publisher, bus,
              recorder_token, live_feed=None, live_recorder_token=None) -> None:
    sim.stop()
    if driver is not None:
        driver.stop()
    ws.stop()
    fusion.stop()
    stiffness_mod.get_tracker() and stiffness_mod.get_tracker().stop()
    bus.unsubscribe(recorder_token)
    if live_recorder_token is not None:
        bus.unsubscribe(live_recorder_token)
    if live_feed is not None:
        live_feed.stop()
    subscriber.stop()
    publisher.stop()
    if api_server is not None:
        api_server.should_exit = True
    log.info("backend stack stopped")


if __name__ == "__main__":
    sys.exit(main())
