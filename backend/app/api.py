"""
VITISH 2026 · PS#99 SHM — FastAPI backend (http://localhost:8000).

REST surface for the digital twin and the demo controller:

    GET  /health
    GET  /api/bridges                    hero + 49 regulator bridges
    GET  /api/bridges/geojson            MapLibre FeatureCollection (50 points)
    GET  /api/bridge/{id}/state          current BHI + sub-indices + state
    GET  /api/bridge/{id}/stiffness      f1, EI drift, damage %, FEM mode shapes
    GET  /api/bridge/{id}/history?metric=bhi|rms&limit=N
    GET  /api/bridge/{id}/alerts?limit=N   recent alerts (live bridge)
    POST /api/demo/scenario              {"scenario": "healthy"|"rupture"}

CORS is open because the twin runs on a different port.  The app is state-light:
it reads the shared store (auto-selected Postgres/memory) and publishes control
commands on the shared event bus.

CORS origins are environment-driven (COMPREHENSIVE-ANALYSIS NOW item 4, ENH-07):
``VITISH_CORS_ORIGINS`` = comma-separated exact origins (e.g. the twin's Vite
dev server).  Default when unset: ``http://localhost:5173`` +
``http://127.0.0.1:5173`` — the demo twin's own origin, NOT ``*``.  Set
``VITISH_CORS_ORIGINS=*`` explicitly to reproduce the old wide-open behaviour
(development only; ``allow_credentials`` is then forced off, because browsers
REFUSE to send credentials on a wildcard-origin CORS response anyway).  The API
still binds 0.0.0.0 on the dev box — a public deployment must pin exact origins
and split credentials (ROADMAP line 121, ROADMAP-NEXT §2 SEC-02).
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
from fastapi.responses import Response
from pydantic import BaseModel

from app import __version__, contract  # noqa: E402
from app import bridge_registry  # noqa: E402
from app import deterioration as det_mod  # noqa: E402
from app import edge_node as edge_mod  # noqa: E402
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
)

log = logging.getLogger(__name__)

_DEFAULT_HERO = {"bhi": 87.0, "u": 3.0, "cv": 0.10, "vib": 0.12, "load": 0.19,
                 "state": "GREEN"}
_UPTIME0 = time.time()

# CORS origins (NOW item 4 / ENH-07): env-driven, safe local default.
_DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def cors_origins() -> list[str]:
    """Exact CORS origins for the API.

    ``VITISH_CORS_ORIGINS`` (comma-separated) overrides the demo-local default
    (the twin's Vite dev server on 5173).  A literal ``*`` reproduces the old
    wide-open behaviour for development only.
    """
    raw = os.environ.get("VITISH_CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(_DEFAULT_CORS_ORIGINS)

# actual bound ports (run_all.py may fall back to a free port when 8000/8765
# are busy); reported via /api/config so the twin never hardcodes them.
_api_port: Optional[int] = None


def set_api_port(port: int) -> None:
    global _api_port
    _api_port = port


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
    _origins = cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        # Explicit origins enable credentialed requests; with the wide-open
        # ``*`` override, credentials are forced off (browsers would refuse to
        # send them on a wildcard response anyway).
        allow_credentials=_origins != ["*"],
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
        """Hero state with a DEFAULT_HERO fallback for every field (ROADMAP
        line 92): per-key .get() so a partial store state can never raise
        KeyError, and every key the endpoints read is guaranteed present."""
        st = _store().current_state(settings.bridge_id)
        merged = dict(_DEFAULT_HERO)
        for k in ("bhi", "u", "cv", "vib", "load", "state"):
            v = st.get(k)
            if v is not None:
                merged[k] = v
        merged["ts"] = st.get("ts")
        merged["nodes"] = st.get("nodes", {})
        merged["source"] = st.get("source")
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

    @app.get("/api/manifest")
    def data_manifest() -> dict:
        """D1-5 data-realism manifest — what each channel actually is (real
        Z24 replay vs modeled synthetic), the documented measurement chain, and
        the honesty labels the provenance UI (D1-6) reads.  Also carries the
        NEW-02 site-temperature block (measured Open-Meteo or simulated fallback)."""
        from app import channel_models as cm
        from app import site_temperature as site_temp_mod
        feed = live_mod.get_live_feed()
        return cm.build_manifest(
            settings, cm.get_data_source(),
            live_active=feed is not None,
            live_status=feed.status() if feed else None,
            edge_status=edge_mod.get_edge_status(),
            site_temp=site_temp_mod.get_site_temp())

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
        if bridge_id in edge_mod.EDGE_BRIDGES:
            st = edge_mod.get_edge_status(bridge=bridge_id)
            if st is None:
                raise HTTPException(status_code=404,
                                    detail="edge node monitor not running")
            return {"id": bridge_id,
                    "name": "ESP-01S edge node" if bridge_id == "esp01-1"
                    else "ESP32 edge node",
                    "hero": False, "live": True, **st}
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
        damage %, FEM mode shapes.  Explainability only — never fuses into BHI.
        NEW-02: carries the honest site-temperature block (measured Open-Meteo
        or simulated fallback) alongside the pinned simulated thermal overlay."""
        if bridge_id != settings.bridge_id:
            raise HTTPException(status_code=404, detail="no stiffness model for this bridge")
        tracker = stiffness_mod.get_tracker()
        if tracker is None:
            return {"error": "stiffness tracker not running",
                    "note": "start the stack (python -m app.run_all)"}
        snap = tracker.snapshot()
        from app import site_temperature as site_temp_mod  # lazy: network probe
        snap["site_temp"] = site_temp_mod.get_site_temp()
        return snap

    @app.get("/api/bridge/{bridge_id}/seeded-defect")
    def seeded_defect(bridge_id: str) -> dict:
        """D2-12 seeded-defect narrative: the demo damage scenario as a named,
        physically-grounded EI loss (Z24/S101 benchmark), the FEM f1 it implies,
        and the per-span EI reduction % that was seeded.  Honest by design: the
        loss is the MODEL's injected ground truth, never a claim about the real
        bridge (see the returned ``note``)."""
        if bridge_id != settings.bridge_id:
            raise HTTPException(status_code=404, detail="no seeded-defect model for this bridge")
        from app import simulator as sim_mod
        sim = sim_mod.get_simulator()
        if sim is None:
            return {"error": "simulator not running",
                    "note": "start the stack (python -m app.run_all --demo)"}
        return sim.seeded_state()

    @app.get("/api/bridge/{bridge_id}/deterioration")
    def deterioration(bridge_id: str, years: int = Query(30, ge=1, le=100),
                      rating: str = Query("super", pattern="^(super|sub)$")) -> dict:
        """Markov condition projection under the empirical LTBP fleet prior
        (D1-4/D2-11).  Probabilistic model, never a certified RUL."""
        if bridge_id == settings.bridge_id:
            hero = _live_hero_state()
            bhi = float(hero["bhi"])
        else:
            b = find_bridge(bridge_id)
            if b is None:
                raise HTTPException(status_code=404, detail="bridge not found")
            bhi = float(b["bhi"])
        try:
            return det_mod.bridge_deterioration(bridge_id, bhi, years=years, rating=rating)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except FileNotFoundError:
            # LTBP summary not built yet (item 9, ROADMAP-NEXT) — a clean 503
            # with the remedy instead of an unhandled 500.
            raise HTTPException(
                status_code=503,
                detail="LTBP Markov priors not available — run scripts/ltbp_analyze.py "
                       "to build data/ltbp/analysis/ltbp_summary.json")

    @app.get("/api/fleet/priority")
    def fleet_priority(limit: int = Query(12, ge=1, le=50),
                       rating: str = Query("super", pattern="^(super|sub)$")) -> dict:
        """S1 RUL decision surface — the whole fleet ranked by next-inspection
        year (most urgent first), each bridge carrying its "years to NBI<=4"
        band.  HONEST LABELS: the 49 regulator healths are seeded/illustrative
        (never real inspection data); every number is a Markov projection under
        an empirical LTBP fleet prior, small n — not a certified RUL.  The hero
        bridge is live and marked as such."""
        hero = _live_hero_state()
        bridges = all_bridges(hero_bhi=hero["bhi"], hero_state=hero["state"])
        rows = []
        for b in bridges:
            bhi = float(b["bhi"])
            current = det_mod.condition_from_bhi(bhi)
            nxt = det_mod.next_inspection(rating, current)
            band = det_mod.years_to_poor(rating, current, threshold=4, horizon=30)
            rows.append({
                "id": b["id"],
                "name": b["name"],
                "state": b["state"],
                "bhi": round(bhi, 1),
                "current_condition": current,
                "next_inspection_year": nxt,
                "years_to_poor": band,
                "live": bool(b.get("live", False)),
                "hero": bool(b.get("hero", False)),
            })
        # Most urgent first: earliest next-inspection year, then the band's
        # expected crossing, then BHI.  Never-within-horizon (None) sorts last.
        rows.sort(key=lambda r: (
            r["next_inspection_year"] if r["next_inspection_year"] is not None else 10 ** 9,
            r["years_to_poor"]["expected"] if r["years_to_poor"]["expected"] is not None else 10 ** 9,
            r["bhi"],
        ))
        for i, r in enumerate(rows, start=1):
            r["rank"] = i
        return {
            "count": len(rows),
            "limit": limit,
            "sorted_by": "next_inspection_year asc (most urgent first); "
                         "tie-break years_to_poor.expected",
            "priors_label": det_mod.PRIORS_LABEL,
            "note": ("Prior-driven prioritization view — the 49 regulator "
                     "healths are seeded/illustrative, never real inspection "
                     "data.  Markov projection under an empirical LTBP fleet "
                     "prior, small n — a probabilistic band, not a certified RUL."),
            "rows": rows[:limit],
        }

    @app.get("/api/bridge/{bridge_id}/report.pdf")
    def condition_report_pdf(bridge_id: str):
        """NEW-04 (item 10) — per-bridge regulator-facing condition report as a
        PDF (reportlab platypus).  DRAFT in IRC-118 format, explicitly not
        certified; assembles the live state, D1-3 condition card, Markov
        deterioration (D1-4/D2-11), recent alerts, and NEW-02 site temperature
        with every honesty label verbatim.  Edge nodes keep no deterioration
        model -> 404, consistent with /deterioration."""
        from app import condition_report as cr
        if bridge_id == settings.bridge_id:
            bridge = {"id": bridge_id, "name": HERO["name"],
                      "city": HERO["city"], "state": HERO["state"],
                      "country": HERO["country"], "kind": HERO["kind"],
                      "year_built": HERO["year_built"], "length_m": HERO["length_m"],
                      "hero": True}
            live_state = _live_hero_state()
            alerts = _store().recent_alerts(bridge_id, 50)
        else:
            b = find_bridge(bridge_id)
            if b is None:
                raise HTTPException(status_code=404, detail="bridge not found")
            bridge, live_state, alerts = b, None, None
        report = cr.compose_report(bridge, live_state=live_state, alerts=alerts)
        pdf = cr.pdf_bytes(report)
        return Response(content=pdf, media_type="application/pdf", headers={
            "Content-Disposition":
                f'attachment; filename="{bridge_id}-condition-report.pdf"'})

    @app.get("/api/fleet/report.csv")
    def fleet_report_csv() -> Response:
        """NEW-04 (item 10) — IBMS-inventory CSV for the whole fleet (hero + 49
        regulators), one row per bridge with NBI rating, next-inspection year,
        years-to-poor band, and the IRC-118 draft disclaimer on every row."""
        from app import condition_report as cr
        hero = _live_hero_state()
        bridges = all_bridges(hero_bhi=hero["bhi"], hero_state=hero["state"])
        csv_text = cr.to_csv(cr.inventory_rows(bridges))
        return Response(content=csv_text.encode("utf-8"), media_type="text/csv",
                        headers={"Content-Disposition":
                                 'attachment; filename="vitish-ibms-inventory.csv"'})

    @app.get("/api/bridge/{bridge_id}/condition")
    def condition(bridge_id: str, run_seg: int = Query(0, ge=0, le=1)) -> dict:
        """Regulator condition card from the crack index (D1-3).

        Default: card from the live fused cv sub-index (fast, offline, always
        labeled ``live-cv-subindex``).  ``?run_seg=1`` runs real segmentation on
        a synthetic demo crack frame -> card from real detections
        (``source=segmentation``, YOLO-seg when crack_seg.pt loads).
        """
        from models.fusion import condition as cond_mod
        if bridge_id == settings.bridge_id:
            hero = _live_hero_state()
            cv = float(hero["cv"])
        else:
            b = find_bridge(bridge_id)
            if b is None:
                raise HTTPException(status_code=404, detail="bridge not found")
            cv = 0.15  # illustrative regulator cv sub-index (see regulator_bridges)
        if run_seg:
            import cv2
            from app import cv_feed
            # shared cached detector — the 92 MB YOLO loads ONCE per process,
            # not once per request (ROADMAP line 44)
            det = cv_feed.get_detector()
            frame_path = cv_feed.DEMO_FRAMES / "mild_crack.jpg"
            img = cv2.imread(str(frame_path))
            if img is None:
                from models.cv.inference import demo_frame
                img = demo_frame(size=320, seed=7)
                frame_note = "real segmentation on a synthetic demo crack frame " \
                             "(models/cv.inference.demo_frame)"
            else:
                frame_note = (f"real segmentation on {frame_path.parent.name}/"
                              f"{frame_path.name} (CC0 CrackSeg9k val)")
            dets = det.detect(img)
            mode = "yolo-seg" if "yolo" in det.mode else "heuristic"
            return cond_mod.condition_card(
                dets, mode=mode, frame_note=frame_note)
        return cond_mod.card_from_live_cv(cv)

    @app.get("/api/bridge/{bridge_id}/history")
    def history(bridge_id: str, metric: str = "bhi",
                limit: int = Query(120, ge=1, le=10000)) -> dict:
        if bridge_id == settings.bridge_id or bridge_registry.is_extra(bridge_id):
            # live store for the hero AND for registry extras (item 14): extras
            # are recorded under their own bridge id, so their history is the
            # real fused/per-second rows, never _simulated_history (which would
            # crash on a non-reg-NN id anyway).
            st = _store()
            if metric == "bhi":
                data = st.recent_bhi(bridge_id, limit)
            elif metric == "rms":
                data = st.recent_rms(bridge_id, limit)
            else:
                raise HTTPException(status_code=400, detail="metric must be bhi|rms")
            return {"bridge": bridge_id, "metric": metric, "limit": limit, "data": data}

        if bridge_id in edge_mod.EDGE_BRIDGES:
            if metric != "rms":
                raise HTTPException(status_code=400,
                                    detail="edge node exposes only rms history")
            st = edge_mod.get_edge_status(bridge=bridge_id)
            rows = (st or {}).get("recent_rms", [])
            return {"bridge": bridge_id, "metric": metric, "limit": limit,
                    "data": rows[-limit:]}

        b = find_bridge(bridge_id)
        if b is None:
            raise HTTPException(status_code=404, detail="bridge not found")
        if metric not in ("bhi", "rms"):
            raise HTTPException(status_code=400, detail="metric must be bhi|rms")
        data = _simulated_history(b, metric, limit)
        return {"bridge": bridge_id, "metric": metric, "limit": limit, "data": data}

    @app.get("/api/bridge/{bridge_id}/alerts")
    def alerts_history(bridge_id: str,
                       limit: int = Query(50, ge=1, le=500)) -> dict:
        """Recent alerts for the live bridge (oldest first); empty for regulator
        / edge bridges that keep no alert store (item 7, ROADMAP-NEXT)."""
        if bridge_id == settings.bridge_id:
            st = _store()
            try:
                data = st.recent_alerts(bridge_id, limit)
            except Exception:
                # persistence down — honest empty history rather than a 500
                data = []
            return {"bridge": bridge_id, "limit": limit, "alerts": data}
        return {"bridge": bridge_id, "limit": limit, "alerts": []}

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
        from app import ws_bridge as ws_mod
        ws_port = ws_mod.get_bound_port() or settings.ws_port
        return {
            "bridge": settings.bridge_id,
            "nodes": settings.nodes,
            "fs": settings.fs,
            "window_n": settings.window_n,
            "window_s": settings.window_s,
            "api_port": _api_port or settings.api_port,
            "ws_port": ws_port,
            "broker": {"host": settings.broker_host, "port": settings.broker_port},
            "demo_speed": settings.demo_speed,
            # BHI contract (ENH-10): the single served source of truth for the
            # fusion constants the twin's computeBhi mirrors.  A consumer that
            # wants to render BHI without importing backend code reads this block
            # and derives computeBhi from it (weights, band thresholds, factors).
            "bhi": {
                "formula": "bhi = 100 * (1 - w_cv*cv - w_vib*vib - w_load*load)"
                           " * age_factor * traffic_factor",
                "weights": dict(contract.BHI_W),
                "green": contract.BHI_GREEN,
                "amber": contract.BHI_AMBER,
                "age_factor": contract.AGE_FACTOR,
                "traffic_factor": contract.TRAFFIC_FACTOR,
            },
            # item 14 (bridge registry): the multi-bridge surface + the honest
            # scope for onboarding.  Extras are env-registered SIMULATED bridges;
            # the label answers "how fast can you onboard a bridge?" without
            # overclaiming — config+registry is a same-run SOFTWARE exercise, a
            # real (sensor) deployment is a days-scale task.
            "multi_bridge": {
                "extra_bridges": bridge_registry.extra_bridges(),
                "onboard_label": bridge_registry.ONBOARD_LABEL,
            },
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
                print(f"[warn] API port {port} busy -- using {alt} instead")
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
