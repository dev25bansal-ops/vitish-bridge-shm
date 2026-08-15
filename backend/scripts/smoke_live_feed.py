"""Ad-hoc smoke test for the live public-broker feed (task #18).

Connects to test.mosquitto.org (or a local broker), streams for up to WINDOW
seconds, and prints the LiveFeed status plus what the live-demo recorder
persisted. Uses a MemoryStore so this needs no Docker/Postgres.

Modes (ROADMAP line 90 — reproducibility):
  default        live connect to test.mosquitto.org (intermittent — may be idle;
                 a FAIL with received=0 honestly means no bytes flowed).
  --local-broker connect to a local MQTT broker (127.0.0.1:1883, override host
                 via VITISH_LOCAL_BROKER=host[:port]) so the smoke never depends
                 on the public broker.
  --no-network   deterministic, ZERO network: injects sample MSU/SHM messages
                 straight through the REAL LiveFeed._on_message -> _adapt ->
                 bus.publish -> recorder chain and asserts the same PASS
                 criterion as the live path. No broker, no waiting.

WINDOW is overridable via VITISH_SMOKE_WINDOW (seconds).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, setup_logging  # noqa: E402
from app import db, events, live_feed  # noqa: E402

# Deterministic sample messages for --no-network, mirroring the LIVE_TOPICS
# shapes verified on the public broker 2026-08-13: an RMS scalar (persisted accel
# row), a Vel scalar (telemetry), a Temperature, and a 1 Hz SHM DAQ JSON blob.
_SAMPLE_MSGS = [
    ("MSU/Accelerometer/RMS/Z/LOC_MSU-A1", {"value": 0.042}),
    ("MSU/Accelerometer/Vel/X/LOC_MSU-A1", {"value": 0.11}),
    ("MSU/Temperature/1", {"value": 21.4}),
    ("shm/usb3134a/data", {"value": 1.2, "units": "mm/s"}),
]


def _run(mode: str, window: float) -> int:
    setup_logging()
    cfg = Settings()
    bus = events.get_bus()

    # tap the bus so we can see exactly which live topics adapt & publish
    topics_seen = []
    def _tap(topic, payload):
        topics_seen.append(topic)
    bus.subscribe("bridge/live-demo/#", _tap)

    store = db.MemoryStore(bridge="live-demo")
    token = db.attach_recorder(cfg, bus, store, pattern="bridge/live-demo/#")

    if mode == "local":
        endpoint = os.environ.get("VITISH_LOCAL_BROKER", "127.0.0.1:1883")
        host, _, port = endpoint.partition(":")
        feed = live_feed.LiveFeed(bus, broker_host=host, broker_port=int(port or 1883))
    else:
        feed = live_feed.LiveFeed(bus)
    live_feed.set_live_feed(feed)

    print(f"mode={mode} window={window:.0f}s broker={feed.broker_host}:{feed.broker_port}")

    if mode == "no-network":
        # deterministic: drive the real adapt/publish/persist chain with sample
        # payloads — no broker, no network, no waiting.
        for topic, payload in _SAMPLE_MSGS:
            msg = SimpleNamespace(topic=topic, payload=json.dumps(payload).encode())
            feed._on_message(None, None, msg)
    else:
        feed.start()
        deadline = time.time() + window
        while time.time() < deadline and feed.received == 0:
            time.sleep(0.5)

    print("\n--- live bus events emitted ---")
    for t in topics_seen[:20]:
        print(f"  {t}")

    print("\n--- LiveFeed.status() ---")
    for k, v in feed.status().items():
        print(f"  {k}: {v}")

    print("\n--- persisted live-demo accel rows (store.rms) ---")
    rows = list(store.rms)
    print(f"  total accel rows persisted: {len(rows)}")
    for ts, node, rms, flag in rows[-8:]:
        print(f"  ts={ts:.1f} node={node} rms={rms:.6g} flag={flag}")

    print("\n--- /api/live shape (get_live_feed) ---")
    st = live_feed.get_live_feed().status()
    print(f"  enabled={st['enabled']} connected={st['connected']} "
          f"received={st['received']} published={st['published']}")

    feed.stop()
    bus.unsubscribe(token)
    ok = feed.received > 0 and feed.published > 0 and len(rows) > 0
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'} "
          f"(received={feed.received} published={feed.published} rows={len(rows)})")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--no-network", action="store_true",
                   help="deterministic: inject sample messages, no broker")
    g.add_argument("--local-broker", action="store_true",
                   help="connect to VITISH_LOCAL_BROKER (default 127.0.0.1:1883) "
                        "instead of test.mosquitto.org")
    ap.add_argument("--window", type=float, metavar="SECS",
                    help="listen seconds (default $VITISH_SMOKE_WINDOW or 75)")
    args = ap.parse_args()
    window = args.window if args.window is not None \
        else float(os.environ.get("VITISH_SMOKE_WINDOW", "75"))
    mode = "no-network" if args.no_network else ("local" if args.local_broker else "public")
    return _run(mode, window)


if __name__ == "__main__":
    sys.exit(main())
