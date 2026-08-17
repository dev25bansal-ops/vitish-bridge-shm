"""Item 13 · Postgres SQL path + failover latch — integration script for CI.

Runs against a LIVE PostgreSQL (the `pg-store` CI job starts a postgres:16
service and sets VITISH_DB_DSN) and exercises the REAL SQL path the backend's
persistence layer uses:

    1. Round-trip fidelity   — insert accel/bhi/alert, read them back with the
       exact values + types, newest-first ordering, PER-BRIDGE scoping
       (z24 rows never leak into a second bridge's reads and vice versa).
    2. Durability across sessions — close the store, reopen a fresh connection
       (create_tables=False), the rows are still there.
    3. Runtime-failover latch — kill the live connection mid-flight; three
       inserts must mirror into the in-memory ring WITHOUT raising; the paced
       reconnect succeeds and resumes Postgres; the degraded-window row is
       served from memory only (never silently back-filled into SQL).

Honest gating: the script needs VITISH_DB_DSN.  Locally, a missing DSN prints
PG_PATH=SKIP and exits 0 so the deterministic runner never depends on Docker.
Under CI=1 a SKIP is a FAIL (no silent SKIP — the pg-store job always sets the
DSN, so the gate must actually run real SQL evidence).

This script is deliberately NOT in scripts/run_tests.sh: the main suite stays
air-gapped/Postgres-free; only the dedicated CI job exercises it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("VITISH_SITE_TEMP_DISABLE", "1")
_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
for p in (_BACKEND, _REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app import db as db_mod  # noqa: E402

DSN = os.environ.get("VITISH_DB_DSN", "").strip()
if not DSN:
    print("PG_PATH=SKIP (VITISH_DB_DSN unset — run with a Postgres, e.g. "
          "docker compose up; CI always sets it via the pg-store job)")
    sys.exit(0 if os.environ.get("CI") != "1" else 1)

print(f"PG_PATH=RUN dsn={DSN.split('@')[-1]}  (real SQL path + failover latch)")
_FAILS = []


def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  FAIL  {name}  {detail}")
        _FAILS.append(name)


# -- 1. round-trip fidelity + per-bridge scoping + ordering -------------------
store = db_mod.PostgresStore(DSN)   # creates tables if needed
try:
    # accel (two nodes, one flagged) + bhi (two timestamps, newest AMBER) + alert
    store.insert_accel(node=1, ts=100.0, rms=3.07e-05, flag=0, bridge="z24")
    store.insert_accel(node=2, ts=100.0, rms=1.84e-04, flag=1, bridge="z24")
    store.insert_bhi(ts=1000.0, bhi=87.1, u=0.1, cv=0.2, vib=0.3,
                     load=0.4, state="GREEN", bridge="z24")
    store.insert_bhi(ts=1001.0, bhi=67.5, u=0.1, cv=0.4, vib=0.35,
                     load=0.15, state="AMBER", bridge="z24")
    store.insert_bhi(ts=1002.0, bhi=55.5, u=0.0, cv=0.6, vib=0.0,
                     load=0.4, state="RED", bridge="reg-001")
    store.insert_alert(ts=1000.5, severity="info", source="fusion",
                       text="seeded-defect window", recommendation="reinspect",
                       bridge="z24")

    rms = store.recent_rms("z24", limit=10)
    _check("accel round-trips with values + flags",
           {r["node"]: r for r in rms} and
           any(r["node"] == 1 and r["rms"] == 3.07e-05 and r["flag"] == 0 for r in rms) and
           any(r["node"] == 2 and r["rms"] == 1.84e-04 and r["flag"] == 1 for r in rms),
           f"nodes={sorted(r['node'] for r in rms)}")

    bhi = store.recent_bhi("z24", limit=10)
    _check("bhi newest-first ordering (AMBER 67.5 ts=1001 first)",
           bhi and bhi[0]["ts"] == 1001.0 and bhi[0]["bhi"] == 67.5
           and bhi[0]["state"] == "AMBER", f"first={bhi[:1]}")

    other = store.recent_bhi("reg-001", limit=10)
    _check("per-bridge scoping: reg-001 RED 55.5 read back",
           other and other[0]["bhi"] == 55.5 and other[0]["state"] == "RED",
           f"other={other[:1]}")
    _check("per-bridge scoping: z24 reads NEVER leak reg-001 rows",
           not any(r["bhi"] == 55.5 for r in bhi), f"z24_rows={bhi}")

    al = store.recent_alerts("z24", limit=10)
    _check("alert round-trips (text + recommendation)",
           al and al[0]["text"] == "seeded-defect window"
           and al[0]["recommendation"] == "reinspect", f"alerts={al[:1]}")

    st = store.current_state("z24")
    _check("current_state merges latest bhi + per-node rms",
           st["bhi"] == 67.5 and st["state"] == "AMBER"
           and set(st["nodes"]) == {"1", "2"}, f"nodes={sorted(st['nodes'])}")

    # -- 2. durability across sessions ------------------------------------------
    store.close()
    reopened = db_mod.PostgresStore(DSN, create_tables=False)  # fresh connection
    try:
        rb = reopened.recent_bhi("z24", limit=10)
        _check("durability: rows survive a fresh connection (real SQL)",
               rb and rb[0]["ts"] == 1001.0 and rb[0]["bhi"] == 67.5,
               f"first={rb[:1]}")
    finally:
        reopened.close()

    # -- 3. runtime-failover latch with a live server ---------------------------
    latch = db_mod.PostgresStore(DSN, create_tables=False)
    try:
        _check("latch starts healthy", latch._degraded is False
               and latch._failures == 0, f"failures={latch._failures}")
        latch.conn.close()          # server connection dies mid-flight
        raised = False
        for i in range(3):          # keep inserting — nothing may raise
            try:
                latch.insert_bhi(ts=2000.0 + i, bhi=12.0, u=0.0, cv=0.5,
                                 vib=0.0, load=0.0, state="AMBER", bridge="z24")
            except Exception as exc:
                raised = True
                print(f"  !!! insert raised in degraded window: {exc!r}")
                break
        _check("degraded inserts never raise (mirror to ring)", not raised)
        _check("latch pins degraded after 3 live failures",
               latch._degraded is True, f"failures={latch._failures}")

        latch._last_reconnect_attempt = 0.0   # force the paced attempt now
        latch._maybe_reconnect()
        _check("paced reconnect resumes live Postgres",
               latch._degraded is False and latch._failures == 0,
               f"degraded={latch._degraded} failures={latch._failures}")

        latch.insert_bhi(ts=3000.0, bhi=42.0, u=0.0, cv=0.1, vib=0.0,
                         load=0.0, state="GREEN", bridge="z24")
        after = latch.recent_bhi("z24", limit=20)
        _check("post-recovery reads come from Postgres (42.0 first)",
               after and after[0]["bhi"] == 42.0, f"first={after[:1]}")
        _check("degraded-window row (12.0) stays volatile, never back-filled",
               not any(r["bhi"] == 12.0 for r in after),
               "ring rows are memory-only by design")
    finally:
        latch.close()

finally:
    try:
        store.close()
    except Exception:
        pass

ok = not _FAILS
print(f"PG_PATH: {'ALL PASS' if ok else 'FAILED'} ({len(_FAILS)} failing)")
sys.exit(0 if ok else 1)