"""COMPREHENSIVE-ANALYSIS item 13 — Postgres failover-latch unit test.

Deterministic, network-free, no Docker: a fake ``psycopg2`` module stands in
for the real driver so the RUNTIME-FAILOVER LATCH in ``PostgresStore``
(degrades to the in-memory ring after repeated write/read failures, then
resumes Postgres on a paced reconnect) is regression-tested in the normal
suite.  The REAL SQL path (round-trip fidelity, durability across sessions,
bridge scoping) is exercised against a live PostgreSQL by the CI job that runs
``backend/scripts/ci_pg_path.py`` — this file stays hermetic.

Three phases, matching db.py's documented contract:

  1. Healthy   — inserts flush to Postgres, ``_failures == 0``, not degraded.
  2. Degrade   — the server connection dies; three consecutive inserts must
                 NOT raise (they mirror into the in-memory ring) and the
                 latch pins ``_degraded``.
  3. Reconnect  — the paced attempt succeeds and swaps in a fresh connection;
                 the latch lifts and new inserts flush to Postgres again.

Honesty assertion: rows written during the degraded window live ONLY in the
volatile ring — after recovery they are served from Postgres and the
degraded-mirror row is no longer returned (nothing is silently merged).
"""
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("VITISH_SITE_TEMP_DISABLE", "1")
_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
for p in (_BACKEND, _REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# -- fake psycopg2 -----------------------------------------------------------
class _FakeClosed(Exception):
    pass


class _FakeConn:
    def __init__(self):
        self.autocommit = False
        self.closed = False
        self.query_results = []   # rows fetchall() returns (mirrors PG state)
        self.calls = []           # (sql, params) executed

    def cursor(self):
        return _FakeCursor(self)

    def close(self):
        self.closed = True


class _FakeCursor:
    def __init__(self, conn):
        self._c = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        if self._c.closed:
            raise _FakeClosed("connection already closed")
        self._c.calls.append((sql, params))

    def fetchall(self):
        return self._c.query_results


_fake = types.ModuleType("psycopg2")


def _fake_connect(dsn, connect_timeout=3):
    return _FakeConn()


_fake.connect = _fake_connect
sys.modules["psycopg2"] = _fake

from app import db as db_mod  # noqa: E402  (must import AFTER the fake is installed)

print("[pg-failover] Postgres runtime-failover latch (fake psycopg2, no server)")
_FAILS = []


def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  FAIL {name}  {detail}")
        _FAILS.append(name)


# -- phase 1: healthy ---------------------------------------------------------
store = db_mod.PostgresStore("fdpostgresql://test")   # fake schema exec succeeds
store.conn.query_results = [(1.0, 87.1, 0.1, 0.2, 0.3, 0.4, "GREEN")]
store.insert_bhi(ts=1.0, bhi=87.1, u=0.1, cv=0.2, vib=0.3, load=0.4,
                 state="GREEN", bridge="z24")
_check("healthy insert flushes to Postgres (no raise)",
       len(store.conn.calls) > 0)
_check("healthy failures == 0", store._failures == 0, f"failures={store._failures}")
_check("not degraded while healthy", store._degraded is False)
rows = store.recent_bhi("z24", limit=5)
_check("recent_bhi round-trips through Postgres",
       rows and rows[0]["bhi"] == 87.1 and rows[0]["state"] == "GREEN",
       f"rows={rows[:1]}")
_check("store source is postgres", store.source == "postgres")

# -- phase 2: degrade ---------------------------------------------------------
store.conn.close()          # the server side dies mid-flight
raised = False
for i in range(3):          # caretakers keep inserting — nothing may raise
    try:
        store.insert_bhi(ts=2.0 + i, bhi=12.0, u=0.0, cv=0.5, vib=0.0,
                         load=0.0, state="AMBER", bridge="z24")
    except Exception as exc:
        raised = True
        print(f"  !!! insert raised during degraded window: {exc!r}")
        break
_check("degraded inserts never raise (mirror to in-memory ring)", not raised)
_check("latch pins degraded after 3 failures",
       store._degraded is True, f"failures={store._failures}")
mirrored = store.recent_bhi("z24", limit=5)
_check("degraded reads served from the ring (no crash)",
       any(r["bhi"] == 12.0 and r["state"] == "AMBER" for r in mirrored),
       f"mirrored={mirrored}")

# -- phase 3: reconnect -------------------------------------------------------
store._last_reconnect_attempt = 0.0      # force the paced attempt immediately
store._maybe_reconnect()
_check("paced reconnect lifts the latch",
       store._degraded is False and store._failures == 0,
       f"degraded={store._degraded} failures={store._failures}")
_check("fresh connection installed", store.conn.closed is False)
store.conn.query_results = [(3.0, 42.0, 0.0, 0.1, 0.0, 0.0, "GREEN")]
store.insert_bhi(ts=3.0, bhi=42.0, u=0.0, cv=0.1, vib=0.0, load=0.0,
                 state="GREEN", bridge="z24")
resumed = store.recent_bhi("z24", limit=5)
_check("post-reconnect reads come from Postgres again",
       resumed and resumed[0]["bhi"] == 42.0, f"resumed={resumed[:1]}")
_check("degraded-window row is NOT silently merged into Postgres",
       not any(r["bhi"] == 12.0 for r in resumed),
       "ring rows are volatile by design, never back-filled")

store.close()

ok = not _FAILS
print(f"[pg-failover] {'ALL PASS' if ok else 'FAILED'} ({len(_FAILS)} failing)")
sys.exit(0 if ok else 1)