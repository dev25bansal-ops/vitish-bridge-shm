"""Item 15 verification — HTTP route tests for the newer endpoints.

Covers /api/live, /api/manifest, /api/bridge/{id}/stiffness, /seeded-defect,
/deterioration, /condition (default + run_seg with a fake detector),
/api/config — status codes, payload shape, and the 'tracker/simulator not
running' guards (plus the running paths via fake singletons).
"""
import sys, tempfile
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

import numpy as np
from fastapi.testclient import TestClient

from app import db, contract
from app.config import Settings
from app.api import create_app

print("[api-routes] newer endpoints: live/manifest/stiffness/seeded-defect/deterioration/condition/config")
def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _FAILS.append(name)

_FAILS = []

_tmp = tempfile.mkdtemp(prefix="vitish-routes-test-")
cfg = Settings()
cfg = replace(cfg, state_cache_path=Path(_tmp) / "state.jsonl")  # hermetic cache
db.reset_store()
st = db.get_store(cfg, prefer="memory")
assert st.source == "memory", st.source

client = TestClient(create_app())

# --- /api/live (feed disabled by default) --------------------------------------
r = client.get("/api/live")
_check("live 200 + disabled", r.status_code == 200 and r.json().get("enabled") is False)

# --- /api/config ---------------------------------------------------------------
r = client.get("/api/config")
b = r.json()
_check("config 200", r.status_code == 200)
_check("config fields", all(k in b for k in
       ("bridge", "nodes", "fs", "window_n", "api_port", "ws_port", "broker")))
_check("config window 10.24s @100Hz", b["fs"] == 100 and b["window_n"] == 1024)

# --- /api/manifest (synthetic source, honest labels) ----------------------------
from app import channel_models as cm
cm.set_data_source("synthetic")
r = client.get("/api/manifest")
b = r.json()
_check("manifest 200", r.status_code == 200)
_check("manifest data_source", b.get("data_source") == "synthetic", str(b.get("data_source")))
_check("manifest channels", "channels" in b and len(b["channels"]) >= 1)
_check("manifest honesty labels", "honesty" in b or "note" in str(b), str(list(b.keys())))

# --- /api/bridge/z24/stiffness (tracker not running -> guard) ------------------
r = client.get("/api/bridge/z24/stiffness")
_check("stiffness guard 200 + error", r.status_code == 200
       and "error" in r.json(), str(r.json()))
r = client.get("/api/bridge/reg-01/stiffness")
_check("stiffness only for hero", r.status_code == 404, str(r.status_code))

# --- /api/bridge/z24/seeded-defect (simulator not running -> guard) ------------
r = client.get("/api/bridge/z24/seeded-defect")
_check("seeded-defect guard 200 + error", r.status_code == 200
       and "error" in r.json(), str(r.json()))

# --- /api/bridge/z24/deterioration (LTBP summary present) ----------------------
r = client.get("/api/bridge/z24/deterioration?years=30&rating=super")
b = r.json()
_check("deterioration 200", r.status_code == 200, f"{r.status_code} {b.get('detail')}")
_check("deterioration shape", all(k in b for k in
       ("bridge", "years", "projection", "rating", "source")) or "projection" in str(b),
       str(list(b.keys())))
_check("deterioration honesty label", "prior" in str(b).lower() or "label" in str(b).lower())
# bad query params -> FastAPI 422 (ge=1 / pattern)
r = client.get("/api/bridge/z24/deterioration?years=0")
_check("deterioration years<1 -> 422", r.status_code == 422, str(r.status_code))
r = client.get("/api/bridge/z24/deterioration?rating=bogus")
_check("deterioration bad rating -> 422", r.status_code == 422, str(r.status_code))
# regulator bridge (reg-01 is a real fleet id) + missing bridge
r = client.get("/api/bridge/reg-01/deterioration?years=10&rating=sub")
_check("deterioration regulator 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
r = client.get("/api/bridge/nope/deterioration")
_check("deterioration missing -> 404", r.status_code == 404, str(r.status_code))

# --- /api/bridge/z24/condition (default = live-cv-subindex) --------------------
r = client.get("/api/bridge/z24/condition")
b = r.json()
_check("condition 200", r.status_code == 200, str(r.status_code))
_check("condition source live-cv-subindex",
       b.get("source") == "live-cv-subindex", str(b.get("source")))
_check("condition card fields", all(k in b for k in
       ("crack_index", "severity", "condition", "confidence", "note")))

# --- condition run_seg=1 with a FAKE detector -----------------------------------
import models.cv.inference as cv_inf

class _FakeDetector:
    mode = "yolo-seg"   # exercises the "yolo in mode" branch
    def __init__(self, **kwargs):   # duck-typed CrackDetector (accepts weight/conf/iou)
        pass
    def detect(self, image_bgr):
        return [{"conf": 0.9, "severity": 0.30},
                {"conf": 0.7, "severity": 0.15}]

cv_inf.CrackDetector = _FakeDetector
cv_inf.demo_frame = lambda size=320, seed=0: np.zeros((size, size, 3), np.uint8)
r = client.get("/api/bridge/z24/condition?run_seg=1")
b = r.json()
_check("condition run_seg 200", r.status_code == 200, str(r.status_code))
_check("condition source segmentation",
       b.get("source") == "segmentation", str(b.get("source")))
_check("condition run_seg mode yolo-seg",
       b.get("detector_mode") == "yolo-seg", str(b.get("detector_mode")))
_check("condition run_seg evidence 2 dets",
       b.get("evidence", {}).get("n_detections") == 2, str(b.get("evidence")))

# --- running paths via fake singletons ------------------------------------------
from app import stiffness as stiff_mod, simulator as sim_mod, live_feed as live_mod

class _FakeTracker:
    def snapshot(self):
        return {"f1_meas": 3.80, "f1_ref": 3.80, "damage_pct": 0.0,
                "ei_drift_pct": 0.0, "freqs": [3.8, 10.15], "baseline_locked": True}

class _FakeSim:
    def seeded_state(self):
        return {"model": "z24 continuous 3-span box girder", "active": [],
                "f1": 3.80, "f1_ref": 3.80, "note": "seeded model defect"}

class _FakeFeed:
    def status(self):
        return {"enabled": True, "broker": "test.mosquitto.org", "connected": True,
                "received": 42, "published": 42}

stiff_mod.set_tracker(_FakeTracker())
sim_mod.set_simulator(_FakeSim())
live_mod.set_live_feed(_FakeFeed())

r = client.get("/api/bridge/z24/stiffness")
b = r.json()
_check("stiffness running 200 + payload", r.status_code == 200
       and "error" not in b and b.get("f1_meas") == 3.80, str(b)[:120])
_check("stiffness baseline_locked", b.get("baseline_locked") is True)
r = client.get("/api/bridge/z24/seeded-defect")
b = r.json()
_check("seeded-defect running 200 + payload", r.status_code == 200
       and "error" not in b and b.get("f1") == 3.80, str(b)[:120])
_check("seeded-defect honesty note", "note" in b and "seeded" in b["note"])
r = client.get("/api/live")
b = r.json()
_check("live running enabled", b.get("enabled") is True and b.get("received") == 42,
       str(b)[:120])
_check("live hero untouched label", b.get("hero_bridge_untouched") is True)

# --- CORS origins (NOW item 4 / ENH-07): env-driven, safe local default ---------
from app.api import cors_origins
_check("cors default origins scoped to twin (not *)",
       cors_origins() == ["http://localhost:5173", "http://127.0.0.1:5173"],
       str(cors_origins()))
import os as _os
_cors_mw = [m for m in create_app().user_middleware
            if getattr(m, "cls", None) is not None and "CORS" in m.cls.__name__]
_check("cors middleware present", len(_cors_mw) == 1)
if _cors_mw:
    kw = dict(_cors_mw[0].kwargs)
    _check("cors allow_origins scoped to twin",
           kw.get("allow_origins") == ["http://localhost:5173",
                                       "http://127.0.0.1:5173"],
           str(kw.get("allow_origins")))
    _check("cors credentials allowed for explicit origins",
           kw.get("allow_credentials") is True)
_os.environ["VITISH_CORS_ORIGINS"] = "http://localhost:3000,http://127.0.0.1:3000"
_check("cors env override",
       cors_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"],
       str(cors_origins()))
_os.environ["VITISH_CORS_ORIGINS"] = "*"
_check("cors wildcard override", cors_origins() == ["*"], str(cors_origins()))
_mw2 = [m for m in create_app().user_middleware
        if getattr(m, "cls", None) is not None and "CORS" in m.cls.__name__]
if _mw2:
    kw2 = dict(_mw2[0].kwargs)
    _check("cors wildcard forces credentials off", kw2.get("allow_credentials") is False,
           str(kw2.get("allow_credentials")))
del _os.environ["VITISH_CORS_ORIGINS"]

# --- cleanup: clear the fake singletons so later suite runs are clean -----------
stiff_mod.set_tracker(None)
sim_mod.set_simulator(None)
live_mod.set_live_feed(None)

print("\nRESULT", "FAIL" if _FAILS else "PASS", len(_FAILS), "failures")
sys.exit(1 if _FAILS else 0)
