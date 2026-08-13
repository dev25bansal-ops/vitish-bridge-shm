"""Ad-hoc smoke test for the live public-broker feed (task #18).

Connects to test.mosquitto.org, streams for up to WINDOW seconds, and prints
the LiveFeed status plus what the live-demo recorder persisted. Uses a
MemoryStore so this needs no Docker/Postgres.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, setup_logging  # noqa: E402
from app import db, events, live_feed  # noqa: E402

WINDOW = 75  # seconds to listen (MSU batch cadence is ~12s, intermittent)
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

feed = live_feed.LiveFeed(bus)
live_feed.set_live_feed(feed)
feed.start()

deadline = time.time() + WINDOW
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
sys.exit(0 if ok else 1)
