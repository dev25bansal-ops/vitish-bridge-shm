"""
VITISH 2026 · PS#99 SHM — FastAPI backend (http://localhost:8000).

REST surface for the digital twin and the demo controller:

    GET  /health
    GET  /api/bridges                    hero + 49 regulator bridges
    GET  /api/bridges/geojson            MapLibre FeatureCollection (50 points)
    GET  /api/bridge/{id}/state          current BHI + sub-indices + state
    GET  /api/bridge/{id}/stiffness      f1, EI drift, damage %, FEM mode shapes
    GET  /api/bridge/{id}/history?metric=bhi|rms&limit=N
    POST /api/demo/scenario              {"scenario": "healthy"|"rupture"}

CORS is open because the twin runs on a different port.  The app is state-light:
it reads the shared store (auto-selected Postgres/memory) and publishes control
commands on the shared event bus.
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import List, Literal, Optional

# launch bootstrap (works from repo root or backend/)
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import __version__, contract  # noqa: E402
from app import live_feed as live_mod  # noqa: E402
from app import stiffness as stiffness_mod  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import get_store, reset_store  # noqa: E402
from app.events import get_bus  # noqa: E402
from app.regulator_bridges import (  # noqa: E402
    HERO,
    all_bridges,
    find_bridge,
    geojson as bridges_geojson,
    simulated_health,
)

log = logging.getLogger(__name__)

_DEFAULT_HERO = {"bhi": 87.0, "u": 3.0, "cv": 0.10, "vib": 0.12, "load": 0.19,
                 "state": "GREEN"}
_UPTIME0 = time.time()


class ScenarioRequest(BaseModel):
    scenario: Literal["healthy", "rupture"]


# ---------------------------------------------------------------------------
# app factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title="VITISH SHM Backend",
        description="PS#99 bridge structural-health pipeline (simulator / MQTT / fusion / API)",
        version=__version__,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- helpers ----------------------------------------------------------------
    def _store():
        return get_store(settings)

    def _broker_reachable() -> bool:
        try:
            with socket.create_connection(
                (settings.broker_host, settings.broker_port), timeout=0.4
            ):
                return True
        except OSError:
            return False

    def _live_hero_state() -> dict:
        st = _store().current_state(settings.bridge_id)
        merged = dict(_DEFAULT_HERO)
        if st.get("bhi") is not None:
            merged.update({k: st[k] for k in ("bhi", "u", "cv", "vib", "load", "state")})
        merged.update({"ts": st.get("ts"), "nodes": st.get("nodes", {}),
                       "source": st.get("source")})
        return merged

    # -- endpoints ----------------------------------------------------------------
    @app.get("/health")
    def health() -> dict:
        st = _store()
        return {
            "status": "ok",
            "service": "vitish-shm-backend",
            "version": __version__,
            "uptime_s": round(time.time() - _UPTIME0, 1),
            "ts": contract.now(),
            "store": getattr(st, "source", "postgres"),
            "broker": {
                "host": settings.broker_host,
                "port": settings.broker_port,
                "reachable": _broker_reachable(),
            },
            "nodes": settings.nodes,
            "bridge": settings.bridge_id,
        }

    @app.get("/api/live")
    def live_status() -> dict:
        """Live public-broker MQTT ingestion status (bridge='live-demo')."""
        feed = live_mod.get_live_feed()
        if feed is None:
            return {"enabled": False,
                    "note": "start the stack with --live (or VITISH_LIVE=1)"}
        st = feed.status()
        st["hero_bridge_untouched"] = True  # live-demo is never fused into z24 BHI
        return st

    @app.get("/api/bridges")
    def bridges() -> dict:
        hero = _live_hero_state()
        return {
            "count": len(all_bridges()),
            "hero": all_bridges(hero_bhi=hero["bhi"], hero_state=hero["state"])[0],
            "bridges": all_bridges(hero_bhi=hero["bhi"], hero_state=hero["state"]),
        }

    @app.get("/api/bridges/geojson")
    def geojson_endpoint() -> dict:
        hero = _live_hero_state()
        return bridges_geojson(hero_bhi=hero["bhi"], hero_state=hero["state"])

    @app.get("/api/bridge/{bridge_id}/state")
    def bridge_state(bridge_id: str) -> dict:
        if bridge_id == settings.bridge_id:
            hero = _live_hero_state()
            return {
                "id": bridge_id,
                "name": HERO["name"],
                "location": f"{HERO['city']}, {HERO['state']}, {HERO['country']}",
                **hero,
                "hero": True,
                "live": True,
            }
        b = find_bridge(bridge_id)
        if b is None:
            raise HTTPException(status_code=404, detail="bridge not found")
        return {"id": b["id"], "name": b["name"],
                "location": f"{b['city']}, {b['state']}",
                "bhi": b["bhi"], "state": b["state"],
                "cv": 0.15, "vib": 0.15, "load": 0.20, "u": 3.0,
                "hero": False, "live": False}

    @app.get("/api/bridge/{bridge_id}/stiffness")
    def stiffness(bridge_id: str) -> dict:
        """Z24 box-girder physics overlay: measured f1, EI drift, model-inferred
        damage %, FEM mode shapes.  Explainability only — never fuses into BHI."""
        if bridge_id != settings.bridge_id:
            raise HTTPException(status_code=404, detail="no stiffness model for this bridge")
        tracker = stiffness_mod.get_tracker()
        if tracker is None:
            return {"error": "stiffness tracker not running",
                    "note": "start the stack (python -m app.run_all)"}
        return tracker.snapshot()

    @app.get("/api/bridge/{bridge_id}/history")
    def history(bridge_id: str, metric: str = "bhi",
                limit: int = Query(120, ge=1, le=10000)) -> dict:
        if bridge_id == settings.bridge_id:
            st = _store()
            if metric == "bhi":
                data = st.recent_bhi(bridge_id, limit)
            elif metric == "rms":
                data = st.recent_rms(bridge_id, limit)
            else:
                raise HTTPException(status_code=400, detail="metric must be bhi|rms")
            return {"bridge": bridge_id, "metric": metric, "limit": limit, "data": data}

        b = find_bridge(bridge_id)
        if b is None:
            raise HTTPException(status_code=404, detail="bridge not found")
        if metric not in ("bhi", "rms"):
            raise HTTPException(status_code=400, detail="metric must be bhi|rms")
        data = _simulated_history(b, metric, limit)
        return {"bridge": bridge_id, "metric": metric, "limit": limit, "data": data}

    @app.post("/api/demo/scenario")
    def demo_scenario(req: ScenarioRequest) -> dict:
        bus = get_bus()
        bus.publish("control/cmd",
                    {"cmd": "scenario", "scenario": req.scenario, "source": "api"},
                    source="api")
        log.info("API: demo scenario -> %s", req.scenario)
        return {"ok": True, "scenario": req.scenario}

    @app.get("/api/config")
    def api_config() -> dict:
        return {
            "bridge": settings.bridge_id,
            "nodes": settings.nodes,
            "fs": settings.fs,
            "window_n": settings.window_n,
            "window_s": settings.window_s,
            "ws_port": settings.ws_port,
            "broker": {"host": settings.broker_host, "port": settings.broker_port},
            "demo_speed": settings.demo_speed,
        }

    return app


def _simulated_history(bridge: dict, metric: str, limit: int) -> List[dict]:
    """Deterministic plausible history for regulator (non-live) bridges."""
    import numpy as np
    seed = int(bridge["id"].replace("reg-", "")) + 1000
    rng = np.random.default_rng(seed)
    now = contract.now()
    step = 60.0
    points = min(limit, 90)
    if metric == "bhi":
        base = bridge["bhi"]
        trend = np.linspace(0, -4.0 if bridge["state"] == "RED" else -1.5, points)
        noise = rng.normal(0, 1.2, points)
        out = []
        for i in range(points):
            ts = now - (points - 1 - i) * step
            v = float(base + trend[i] + noise[i])
            out.append({"ts": ts, "bhi": round(max(0.0, min(100.0, v)), 1),
                        "u": 3.0, "state": contract.state_for(v)})
        return out
    # rms
    nodes = settings.nodes
    out = []
    for node in nodes:
        base = 0.03 + 0.01 * (node % 3)
        noise = rng.normal(0, 0.004, points)
        for i in range(points):
            ts = now - (points - 1 - i) * step
            out.append({"ts": ts, "node": node, "rms": round(float(base + noise[i]), 6),
                        "flag": 0})
    out.sort(key=lambda r: r["ts"])
    return out


# ---------------------------------------------------------------------------
# launcher
# ---------------------------------------------------------------------------
def run(host: Optional[str] = None, port: Optional[int] = None) -> None:
    import socket
    import uvicorn
    host = host or settings.api_host
    port = port or settings.api_port
    try:
        with socket.create_connection((host, port), timeout=0.4):
            # port busy -> walk upward to the first free one
            alt = _find_free_port(host, port + 1)
            if alt is not None:
                print(f"[warn] API port {port} busy — using {alt} instead")
                port = alt
    except OSError:
        pass
    uvicorn.run(create_app(), host=host, port=port)


def _find_free_port(host: str, start: int, attempts: int = 20) -> Optional[int]:
    import socket
    for p in range(start, start + attempts):
        try:
            with socket.create_connection((host, p), timeout=0.4):
                continue
        except OSError:
            return p
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"VITISH SHM API  ->  http://localhost:{settings.api_port}")
    run()
