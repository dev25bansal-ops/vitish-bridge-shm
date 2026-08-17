"""
VITISH 2026 · PS#99 SHM — persistence layer.

Two implementations behind one ``Store`` interface:

* :class:`PostgresStore` — psycopg2 against the docker-compose database.  Has a
  runtime-failover latch (item 8, ROADMAP-NEXT): if Postgres dies after boot,
  repeated write/read failures mirror into an in-memory ring and the store
  degrades to memory instead of raising per insert; a paced reconnect resumes
  Postgres automatically when it comes back.
* :class:`MemoryStore`   — in-memory ring buffers + a JSON append log at
  ``app/state_cache.json`` that survives restarts.

:func:`get_store` auto-selects: it tries Postgres and falls back to memory when
the database is unreachable, so the demo NEVER breaks without Docker.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from app import contract
from app.config import Settings

log = logging.getLogger(__name__)

_MAX_SERIES = 8192        # accel / bhi points kept in memory
_MAX_ALERTS = 512
_CACHE_MAX_LINES = 20000  # compact the JSON log beyond this
_DEGRADE_AFTER = 3        # consecutive Postgres failures before latching to memory
_RECONNECT_EVERY = 10.0   # seconds between reconnect attempts once degraded


# ---------------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------------
class Store:
    source = "abstract"

    def insert_accel(self, node: int, ts: float, rms: float, flag: int,
                     bridge: Optional[str] = None) -> None: ...
    def insert_bhi(self, ts: float, bhi: float, u: float, cv: float, vib: float,
                   load: float, state: str, bridge: Optional[str] = None) -> None: ...
    def insert_alert(self, ts: float, severity: str, source: str, text: str,
                     recommendation: str, bridge: Optional[str] = None) -> None: ...
    def recent_rms(self, bridge: str, limit: int = 120) -> List[dict]: ...
    def recent_bhi(self, bridge: str, limit: int = 120) -> List[dict]: ...
    def recent_alerts(self, bridge: str, limit: int = 50) -> List[dict]: ...
    def current_state(self, bridge: str) -> dict: ...
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------
class PostgresStore(Store):
    source = "postgres"

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS accel (
        id     BIGSERIAL PRIMARY KEY,
        bridge TEXT NOT NULL DEFAULT 'z24',
        node   INT  NOT NULL,
        ts     DOUBLE PRECISION NOT NULL,
        rms    DOUBLE PRECISION NOT NULL,
        flag   SMALLINT NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_accel_ts   ON accel (bridge, ts);
    CREATE INDEX IF NOT EXISTS idx_accel_node ON accel (bridge, node, ts);

    CREATE TABLE IF NOT EXISTS bhi (
        id    BIGSERIAL PRIMARY KEY,
        bridge TEXT NOT NULL DEFAULT 'z24',
        ts    DOUBLE PRECISION NOT NULL,
        bhi   DOUBLE PRECISION NOT NULL,
        u     DOUBLE PRECISION NOT NULL,
        cv    DOUBLE PRECISION NOT NULL,
        vib   DOUBLE PRECISION NOT NULL,
        load  DOUBLE PRECISION NOT NULL,
        state TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_bhi_ts ON bhi (bridge, ts);

    CREATE TABLE IF NOT EXISTS alerts (
        id             BIGSERIAL PRIMARY KEY,
        bridge         TEXT NOT NULL DEFAULT 'z24',
        ts             DOUBLE PRECISION NOT NULL,
        severity       TEXT NOT NULL,
        source         TEXT NOT NULL,
        text           TEXT NOT NULL,
        recommendation TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (bridge, ts);
    """

    def __init__(self, dsn: str, create_tables: bool = True) -> None:
        import psycopg2  # local import: only needed when Postgres is used
        self._dsn = dsn
        # Runtime-failover ring (item 8, ROADMAP-NEXT): on repeated write/read
        # failure we latch to this in-memory ring so persistence degrades to
        # memory instead of raising per insert; a paced reconnect resumes
        # Postgres when it comes back.  Honest: the ring is bounded and volatile.
        self._ring = MemoryStore(bridge=contract.BRIDGE_ID)
        self._failures = 0
        self._degraded = False
        self._last_reconnect_attempt = 0.0
        self._pg_lock = threading.RLock()  # guards conn swap + persist attempts
        self.conn = psycopg2.connect(dsn, connect_timeout=3)
        self.conn.autocommit = True
        if create_tables:
            with self.conn.cursor() as cur:
                cur.execute(self._SCHEMA)
        log.info("Postgres store ready")

    # -- runtime-failover machinery -------------------------------------------
    def _mark_ok(self) -> None:
        self._failures = 0

    def _mark_failed(self, exc: Exception) -> None:
        with self._pg_lock:
            self._failures += 1
            if self._failures >= _DEGRADE_AFTER and not self._degraded:
                self._degraded = True
                self._last_reconnect_attempt = time.monotonic()
                log.error(
                    "Postgres persistence failing (%s) — DEGRADED to in-memory ring; "
                    "reconnect attempts continue every %.0fs", exc, _RECONNECT_EVERY)

    def _maybe_reconnect(self) -> None:
        """Paced reconnect attempt while degraded; resumes Postgres on success."""
        now = time.monotonic()
        if now - self._last_reconnect_attempt < _RECONNECT_EVERY:
            return
        self._last_reconnect_attempt = now
        try:
            import psycopg2
            newconn = psycopg2.connect(self._dsn, connect_timeout=3)
            newconn.autocommit = True
            with newconn.cursor() as cur:
                cur.execute(self._SCHEMA)
        except Exception as exc:
            log.warning("Postgres still down after reconnect: %s", exc)
            return
        with self._pg_lock:
            old = self.conn
            self.conn = newconn
            self._failures = 0
            self._degraded = False
        try:
            old.close()
        except Exception:
            pass
        log.info("Postgres store reconnected — persistence resumed")

    def _exec(self, sql: str, params: tuple) -> None:
        with self._pg_lock:
            with self.conn.cursor() as cur:
                cur.execute(sql, params)

    def _query(self, sql: str, params: tuple, limit: int):
        with self._pg_lock:
            with self.conn.cursor() as cur:
                cur.execute(sql + " LIMIT %s", params + (limit,))
                return cur.fetchall()

    def insert_accel(self, node, ts, rms, flag, bridge=None) -> None:
        if self._degraded:
            self._ring.insert_accel(node, ts, rms, flag, bridge=bridge)
            self._maybe_reconnect()
            return
        try:
            self._exec(
                "INSERT INTO accel (bridge, node, ts, rms, flag) VALUES (%s,%s,%s,%s,%s)",
                (bridge or contract.BRIDGE_ID, int(node), float(ts), float(rms), int(flag)),
            )
            self._mark_ok()
        except Exception as exc:
            self._ring.insert_accel(node, ts, rms, flag, bridge=bridge)
            self._mark_failed(exc)

    def insert_bhi(self, ts, bhi, u, cv, vib, load, state, bridge=None) -> None:
        if self._degraded:
            self._ring.insert_bhi(ts, bhi, u, cv, vib, load, state, bridge=bridge)
            self._maybe_reconnect()
            return
        try:
            self._exec(
                "INSERT INTO bhi (bridge, ts, bhi, u, cv, vib, load, state) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (bridge or contract.BRIDGE_ID, float(ts), float(bhi), float(u),
                 float(cv), float(vib), float(load), str(state)),
            )
            self._mark_ok()
        except Exception as exc:
            self._ring.insert_bhi(ts, bhi, u, cv, vib, load, state, bridge=bridge)
            self._mark_failed(exc)

    def insert_alert(self, ts, severity, source, text, recommendation, bridge=None) -> None:
        if self._degraded:
            self._ring.insert_alert(ts, severity, source, text, recommendation, bridge=bridge)
            self._maybe_reconnect()
            return
        try:
            self._exec(
                "INSERT INTO alerts (bridge, ts, severity, source, text, recommendation) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (bridge or contract.BRIDGE_ID, float(ts), str(severity), str(source),
                 str(text), str(recommendation)),
            )
            self._mark_ok()
        except Exception as exc:
            self._ring.insert_alert(ts, severity, source, text, recommendation, bridge=bridge)
            self._mark_failed(exc)

    def _read_ring(self, method: str, *args) -> list:
        return getattr(self._ring, method)(*args)

    def recent_rms(self, bridge, limit=120) -> List[dict]:
        if self._degraded:
            self._maybe_reconnect()
            return self._read_ring("recent_rms", bridge, limit)
        try:
            rows = self._query(
                "SELECT ts, node, rms, flag FROM accel WHERE bridge=%s ORDER BY ts DESC",
                (bridge,), max(limit, 1),
            )
            return [{"ts": r[0], "node": r[1], "rms": r[2], "flag": r[3]}
                    for r in reversed(rows)]
        except Exception as exc:
            self._mark_failed(exc)
            return self._read_ring("recent_rms", bridge, limit)

    def recent_bhi(self, bridge, limit=120) -> List[dict]:
        if self._degraded:
            self._maybe_reconnect()
            return self._read_ring("recent_bhi", bridge, limit)
        try:
            rows = self._query(
                "SELECT ts, bhi, u, cv, vib, load, state FROM bhi WHERE bridge=%s "
                "ORDER BY ts DESC",
                (bridge,), max(limit, 1),
            )
            return [{"ts": r[0], "bhi": r[1], "u": r[2], "cv": r[3], "vib": r[4],
                     "load": r[5], "state": r[6]} for r in reversed(rows)]
        except Exception as exc:
            self._mark_failed(exc)
            return self._read_ring("recent_bhi", bridge, limit)

    def recent_alerts(self, bridge, limit=50) -> List[dict]:
        if self._degraded:
            self._maybe_reconnect()
            return self._read_ring("recent_alerts", bridge, limit)
        try:
            rows = self._query(
                "SELECT ts, severity, source, text, recommendation FROM alerts "
                "WHERE bridge=%s ORDER BY ts DESC",
                (bridge,), max(limit, 1),
            )
            return [{"ts": r[0], "severity": r[1], "source": r[2], "text": r[3],
                     "recommendation": r[4]} for r in reversed(rows)]
        except Exception as exc:
            self._mark_failed(exc)
            return self._read_ring("recent_alerts", bridge, limit)

    def current_state(self, bridge) -> dict:
        if self._degraded:
            self._maybe_reconnect()
            return self._ring.current_state(bridge)
        try:
            bhi = self._query(
                "SELECT ts, bhi, u, cv, vib, load, state FROM bhi WHERE bridge=%s "
                "ORDER BY ts DESC", (bridge,), 1,
            )
            rms = self._query(
                "SELECT node, rms, flag FROM accel WHERE bridge=%s ORDER BY ts DESC",
                (bridge,), 100,
            )
        except Exception as exc:
            self._mark_failed(exc)
            return self._ring.current_state(bridge)
        nodes: Dict[str, dict] = {}
        seen: set = set()
        for node, r, flag in rms:  # keep last per node
            if node in seen:
                continue
            seen.add(node)
            nodes[str(node)] = {"rms": r, "flag": int(flag)}
        if bhi:
            ts, b, u, cv, vib, load, state = bhi[0]
        else:
            ts, b, u, cv, vib, load, state = contract.now(), None, None, None, None, None, None
        return {
            "bridge": bridge, "ts": ts, "bhi": b, "u": u, "cv": cv, "vib": vib,
            "load": load, "state": state, "nodes": nodes, "source": self.source,
        }

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Memory (fallback)
# ---------------------------------------------------------------------------
class MemoryStore(Store):
    source = "memory"

    def __init__(self, bridge: str = contract.BRIDGE_ID,
                 cache_path: Optional[Path] = None,
                 max_series: int = _MAX_SERIES, max_alerts: int = _MAX_ALERTS) -> None:
        self.bridge = bridge
        self.cache_path = Path(cache_path) if cache_path else None
        # Every deque row is tagged with its bridge id as the LAST field so reads
        # can be scoped (ENH-01 / BUG-01): recent_rms('z24') must never return a
        # live-demo or edge row.  The public row dict shape is unchanged — the
        # tag is internal only.
        self.rms: Deque[tuple] = deque(maxlen=max_series)      # (ts, node, rms, flag, bridge)
        self.bhi: Deque[tuple] = deque(maxlen=max_series)      # (ts, bhi,u,cv,vib,load,state, bridge)
        self.alerts: Deque[tuple] = deque(maxlen=max_alerts)   # (ts,sev,src,text,rec, bridge)
        self._lock = threading.RLock()
        self._load_cache()
        self._cache_fh = None
        if self.cache_path is not None:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_fh = self.cache_path.open("a", encoding="utf-8")
        log.info("Memory store ready (cache=%s)", self.cache_path or "none")

    # -- persistence ----------------------------------------------------------
    def _load_cache(self) -> None:
        if self.cache_path is None or not self.cache_path.exists():
            return
        try:
            lines = self.cache_path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                self._apply_record(rec)
            # truncate: memory now holds the state; restart the log fresh
            self.cache_path.write_text("", encoding="utf-8")
            log.info("reloaded %d cached records from %s", len(lines), self.cache_path)
        except Exception as exc:
            log.warning("could not load state cache (%s)", exc)

    def _apply_record(self, rec: dict) -> None:
        kind, data = rec.get("kind"), rec.get("data") or {}
        # bridge is the LAST tuple field; records written before the bridge-tag
        # (ENH-01) carry no key and are attributed to this store's own bridge.
        bridge = data.get("bridge") or self.bridge
        if kind == "accel":
            self.rms.append((data.get("ts"), data.get("node"), data.get("rms"),
                             data.get("flag"), bridge))
        elif kind == "bhi":
            self.bhi.append((data.get("ts"), data.get("bhi"), data.get("u"),
                             data.get("cv"), data.get("vib"), data.get("load"),
                             data.get("state"), bridge))
        elif kind == "alert":
            self.alerts.append((data.get("ts"), data.get("severity"), data.get("source"),
                                data.get("text"), data.get("recommendation"), bridge))

    def _log(self, kind: str, data: dict) -> None:
        if self._cache_fh is None:
            return
        try:
            self._cache_fh.write(json.dumps({"kind": kind, "data": data}) + "\n")
            self._cache_fh.flush()
            self._maybe_compact()
        except Exception:
            pass

    def _maybe_compact(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            if self.cache_path.stat().st_size > 2_000_000:
                lines = self.cache_path.read_text(encoding="utf-8").splitlines()
                self.cache_path.write_text("\n".join(lines[-_CACHE_MAX_LINES:]) + "\n", encoding="utf-8")
                self._cache_fh.close()
                self._cache_fh = self.cache_path.open("a", encoding="utf-8")
        except Exception:
            pass

    # -- interface --------------------------------------------------------------
    def insert_accel(self, node, ts, rms, flag, bridge=None) -> None:
        with self._lock:
            bridge = bridge or self.bridge
            self.rms.append((float(ts), int(node), float(rms), int(flag), bridge))
            self._log("accel", {"ts": ts, "node": node, "rms": rms, "flag": flag,
                                "bridge": bridge})

    def insert_bhi(self, ts, bhi, u, cv, vib, load, state, bridge=None) -> None:
        with self._lock:
            bridge = bridge or self.bridge
            self.bhi.append((float(ts), float(bhi), float(u), float(cv),
                             float(vib), float(load), str(state), bridge))
            self._log("bhi", {"ts": ts, "bhi": bhi, "u": u, "cv": cv,
                              "vib": vib, "load": load, "state": state,
                              "bridge": bridge})

    def insert_alert(self, ts, severity, source, text, recommendation, bridge=None) -> None:
        with self._lock:
            bridge = bridge or self.bridge
            self.alerts.append((float(ts), str(severity), str(source),
                                str(text), str(recommendation), bridge))
            self._log("alert", {"ts": ts, "severity": severity, "source": source,
                                "text": text, "recommendation": recommendation,
                                "bridge": bridge})

    def recent_rms(self, bridge, limit=120) -> List[dict]:
        with self._lock:
            rows = [r for r in self.rms if r[-1] == bridge][-max(limit, 1):]
        return [{"ts": r[0], "node": r[1], "rms": r[2], "flag": r[3]} for r in rows]

    def recent_bhi(self, bridge, limit=120) -> List[dict]:
        with self._lock:
            rows = [r for r in self.bhi if r[-1] == bridge][-max(limit, 1):]
        return [{"ts": r[0], "bhi": r[1], "u": r[2], "cv": r[3], "vib": r[4],
                 "load": r[5], "state": r[6]} for r in rows]

    def recent_alerts(self, bridge, limit=50) -> List[dict]:
        with self._lock:
            rows = [r for r in self.alerts if r[-1] == bridge][-max(limit, 1):]
        return [{"ts": r[0], "severity": r[1], "source": r[2], "text": r[3],
                 "recommendation": r[4]} for r in rows]

    def current_state(self, bridge) -> dict:
        with self._lock:
            b = [r for r in self.bhi if r[-1] == bridge]
            last = b[-1] if b else None
            nodes: Dict[str, dict] = {}
            for ts, node, rms, flag, _br in self.rms:
                if _br != bridge:
                    continue
                nodes[str(node)] = {"rms": rms, "flag": flag}
        if last:
            ts, bhi, u, cv, vib, load, state, _br = last
        else:
            ts, bhi, u, cv, vib, load, state = contract.now(), None, None, None, None, None, None
        return {
            "bridge": bridge, "ts": ts, "bhi": bhi, "u": u, "cv": cv, "vib": vib,
            "load": load, "state": state, "nodes": nodes, "source": self.source,
        }

    def close(self) -> None:
        if self._cache_fh is not None:
            try:
                self._cache_fh.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------
_store: Optional[Store] = None
_store_lock = threading.Lock()


def get_store(cfg: Settings, prefer: str = "auto") -> Store:
    """Return a process-wide store, auto-selecting Postgres vs memory.

    ``prefer`` in {"auto", "postgres", "memory"} for tests / force modes.
    """
    global _store
    with _store_lock:
        if _store is not None:
            return _store
        if not cfg.db_dsn:
            # No configured credential (ROADMAP line 92): Postgres is opt-in via
            # VITISH_DB_DSN; empty -> MemoryStore without a doomed connect attempt.
            log.warning("db_dsn empty (set VITISH_DB_DSN to enable Postgres) -> MemoryStore")
            _store = MemoryStore(bridge=cfg.bridge_id, cache_path=cfg.state_cache_path)
            return _store
        if prefer == "postgres":
            _store = PostgresStore(cfg.db_dsn)
            return _store
        try:
            _store = PostgresStore(cfg.db_dsn)
            return _store
        except Exception as exc:
            log.warning("Postgres unreachable (%s) -> MemoryStore fallback", exc)
            _store = MemoryStore(bridge=cfg.bridge_id, cache_path=cfg.state_cache_path)
            return _store


def reset_store() -> None:
    global _store
    with _store_lock:
        _store = None


def attach_recorder(cfg: Settings, bus, store: Store, pattern: Optional[str] = None):
    """Subscribe to telemetry on the event bus and persist it.

    ``pattern`` defaults to the hero bridge (``bridge/{cfg.bridge_id}/#``); pass
    e.g. ``bridge/live-demo/#`` to also record the live public-broker feed into
    the same store (tagged ``bridge='live-demo'``).
    Returns the bus token so the caller can unsubscribe on shutdown.

    Ingestion boundary (ROADMAP line 38): accel rows are validated against the
    frozen contract at the recorder — bridge-aware (hero rows need fs=100 + 100
    samples; live-demo rows are the documented thin RMS-only form).  Invalid
    rows are logged and DROPPED (never raise — the stream keeps flowing).
    """
    def _accel_row_valid(payload: dict, bridge: str) -> bool:
        errors = contract.validate_accel(payload, bridge=bridge)
        if errors:
            log.warning("recorder dropped invalid accel row (bridge=%s): %s",
                        bridge, "; ".join(errors))
            return False
        return True

    def on_event(topic: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        # The recorder subscribes to a bridge-scoped pattern, so the topic
        # itself names the bridge: bridge/<id>/accel|bhi|alert.  Validate and
        # persist under THAT id — a row claiming a different bridge on this
        # topic is inconsistent and must be dropped (ROADMAP line 38).
        parts = topic.split("/")
        bridge = parts[1] if len(parts) > 1 and parts[0] == "bridge" else cfg.bridge_id
        # live-demo /telemetry envelopes fall through to here deliberately: they
        # are unvetted third-party scalars and are NOT persisted (ROADMAP line 91
        # decision — the thin live-demo /accel rows already prove ingestion).
        try:
            if topic.endswith("/accel"):
                if not _accel_row_valid(payload, bridge):
                    return
                store.insert_accel(
                    node=payload.get("node"), ts=payload.get("ts"),
                    rms=payload.get("rms"), flag=payload.get("flag"),
                    bridge=bridge,
                )
            elif topic.endswith("/bhi"):
                bhi = payload.get("bhi")
                try:
                    bhi_ok = math.isfinite(float(bhi)) and 0.0 <= float(bhi) <= 100.0
                except (TypeError, ValueError):
                    bhi_ok = False
                if not bhi_ok:
                    log.warning("recorder dropped invalid bhi row: bhi=%r", bhi)
                    return
                store.insert_bhi(
                    ts=payload.get("ts"), bhi=payload.get("bhi"), u=payload.get("u"),
                    cv=payload.get("cv"), vib=payload.get("vib"),
                    load=payload.get("load"), state=payload.get("state"),
                    bridge=bridge,
                )
            elif topic.endswith("/alert"):
                store.insert_alert(
                    ts=payload.get("ts"), severity=payload.get("severity"),
                    source=payload.get("source"), text=payload.get("text"),
                    recommendation=payload.get("recommendation", ""),
                    bridge=bridge,
                )
        except Exception:
            log.exception("recorder failed on %s", topic)

    return bus.subscribe(pattern or f"bridge/{cfg.bridge_id}/#", on_event)
