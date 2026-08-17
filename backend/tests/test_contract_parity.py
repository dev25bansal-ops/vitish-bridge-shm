"""NOW-5 verification — ENH-01 + ENH-10.

A. /api/config serves the BHI contract block that EXACTLY matches
   backend/app/contract.py (weights / green / amber / age / traffic factors) —
   the single served source of truth.
B. The twin's hand-mirrored constants in twin/src/store.ts (BHI_W, BHI_GREEN,
   BHI_AMBER, AGE_FACTOR, TRAFFIC_FACTOR, FS_HZ, WINDOW_N) equal the backend
   contract + config.  Drift in either direction fails here.
C. Every numeric `computeBhi(...).toBe(...)` assertion pinned in
   twin/src/store.test.ts is RE-EXECUTED against the live backend
   contract.compute_bhi — a real cross-language parity check (the twin's own
   expected values vs the Python reference, incl. the factor cases), plus a
   (cv, vib, load) grid sweep for monotonicity and clamp/round.
D. ENH-01: MemoryStore is bridge-tagged — one store with rows under multiple
   bridge ids isolates recent_rms / recent_bhi / current_state('z24') from
   foreign rows (BUG-01, reproduced previously), and old JSONL records without
   a bridge key still load (attributed to the store's own bridge).
"""
import json
import re
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from fastapi.testclient import TestClient

from app import db, contract
from app.config import Settings
from app.api import create_app

_REPO = Path(__file__).resolve().parents[1].parent  # repo root
_TWIN_STORE = _REPO / "twin" / "src" / "store.ts"
_TWIN_TEST = _REPO / "twin" / "src" / "store.test.ts"

print("[contract-parity] /api/config BHI block + twin constants + computeBhi parity + MemoryStore bridge-tag")
_FAILS: list = []


def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _FAILS.append(name)


# --- A. /api/config serves the BHI contract block -----------------------------
_tmp = tempfile.mkdtemp(prefix="vitish-parity-test-")
cfg = Settings()
cfg = replace(cfg, state_cache_path=Path(_tmp) / "state.jsonl")
db.reset_store()
db.get_store(cfg, prefer="memory")
client = TestClient(create_app())

r = client.get("/api/config")
assert r.status_code == 200, r.text
c = r.json()["bhi"]
_check("config bhi block present", isinstance(c, dict) and "weights" in c, str(r.json().get("bhi")))
_check("config weights == contract.BHI_W",
       c["weights"] == {k: float(v) for k, v in contract.BHI_W.items()}, str(c["weights"]))
_check("config green == contract.BHI_GREEN", c["green"] == contract.BHI_GREEN)
_check("config amber == contract.BHI_AMBER", c["amber"] == contract.BHI_AMBER)
_check("config age_factor == contract.AGE_FACTOR", c["age_factor"] == contract.AGE_FACTOR)
_check("config traffic_factor == contract.TRAFFIC_FACTOR", c["traffic_factor"] == contract.TRAFFIC_FACTOR)
_check("config formula documented", "100" in c.get("formula", "") and "w_cv" in c.get("formula", ""))


# A consumer that only reads /api/config can reproduce compute_bhi from scratch.
def _consumer_compute_bhi(cfg_block, cv, vib, load, age_factor=None, traffic_factor=None):
    w = cfg_block["weights"]
    pen = w["cv"] * max(0.0, min(1.0, cv)) + w["vib"] * max(0.0, min(1.0, vib)) \
        + w["load"] * max(0.0, min(1.0, load))
    af = age_factor if age_factor is not None else cfg_block["age_factor"]
    tf = traffic_factor if traffic_factor is not None else cfg_block["traffic_factor"]
    return round(max(0.0, min(100.0, 100.0 * (1.0 - pen) * af * tf)), 1)


for cv, vib, load in [(0.12, 0.14, 0.3), (0.4, 0.35, 0.25), (1.0, 1.0, 1.0), (0.5, 0.0, 0.0)]:
    got = _consumer_compute_bhi(c, cv, vib, load)
    want = contract.compute_bhi(cv, vib, load)
    _check(f"consumer-derivable computeBhi({cv},{vib},{load}) == contract",
           got == want, f"got {got} want {want}")

# --- B. twin constants == backend contract ------------------------------------
_src = _TWIN_STORE.read_text(encoding="utf-8")
_cfg = client.get("/api/config").json()

def _const(pattern, label, want, src=_src, fmt=float):
    m = re.search(pattern, src)
    _check(f"twin {label} == backend", m is not None and fmt(m.group(1)) == want,
           f"{m.group(1) if m else 'NOT FOUND'} vs {want}")

_const(r"export const BHI_GREEN = ([\d.]+)", "BHI_GREEN", contract.BHI_GREEN)
_const(r"export const BHI_AMBER = ([\d.]+)", "BHI_AMBER", contract.BHI_AMBER)
_const(r"export const AGE_FACTOR = ([\d.]+)", "AGE_FACTOR", contract.AGE_FACTOR)
_const(r"export const TRAFFIC_FACTOR = ([\d.]+)", "TRAFFIC_FACTOR", contract.TRAFFIC_FACTOR)
_const(r"export const FS_HZ = (\d+)", "FS_HZ", _cfg["fs"], fmt=int)
_const(r"export const WINDOW_N = (\d+)", "WINDOW_N", _cfg["window_n"], fmt=int)
m = re.search(r"export const BHI_W = \{ cv: ([\d.]+), vib: ([\d.]+), load: ([\d.]+) \}", _src)
if m:
    twin_w = {"cv": float(m.group(1)), "vib": float(m.group(2)), "load": float(m.group(3))}
    _check("twin BHI_W == contract.BHI_W", twin_w == contract.BHI_W, str(twin_w))
else:
    _check("twin BHI_W == contract.BHI_W", False, "BHI_W not parsed")

# --- C. re-run the twin's pinned computeBhi assertions against the backend ----
_test = _TWIN_TEST.read_text(encoding="utf-8")

# C1: the `cases` it.each grid (cv, vib, load, expected).
case_pat = re.compile(r"\[([-\d.]+),\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\]")
cases = case_pat.findall(_test)
_check("twin test cases array parsed", len(cases) >= 5, f"{len(cases)} parsed")
for cv, vib, load, expected in cases:
    want = contract.compute_bhi(float(cv), float(vib), float(load))
    _check(f"twin case computeBhi({cv},{vib},{load}) == contract {expected}",
           want == float(expected), f"contract says {want}")

# C2: direct numeric assertions computeBhi(...).toBe(N) (the factor cases).
call_pat = re.compile(r"computeBhi\(([-0-9.,\s]+)\)\)?\s*\.toBe\(([-0-9.]+)\)")
calls = call_pat.findall(_test)
_check("twin direct-call assertions parsed", len(calls) >= 3, f"{len(calls)} parsed")
for args, expected in calls:
    nums = [float(a.strip()) for a in args.split(",")]
    if len(nums) == 3:
        want = contract.compute_bhi(*nums)
    elif len(nums) == 4:
        want = contract.compute_bhi(nums[0], nums[1], nums[2], age_factor=nums[3])
    elif len(nums) == 5:
        want = contract.compute_bhi(nums[0], nums[1], nums[2],
                                    age_factor=nums[3], traffic_factor=nums[4])
    else:
        _check(f"twin call parity {args}", False, f"unexpected arg count {len(nums)}")
        continue
    _check(f"twin call computeBhi({args}) == contract {expected}",
           want == float(expected), f"contract says {want}")

# C3: grid sweep — monotone non-increasing in EACH component alone + formula parity.
_grid = [0.0, 0.05, 0.2, 0.5, 0.8, 1.0, 1.5]
_axes = [("cv", 0), ("vib", 1), ("load", 2)]
for axis, idx in _axes:
    for fix1 in _grid:
        for fix2 in _grid:
            other = [0.0, 0.0, 0.0]
            other[(idx + 1) % 3] = fix1
            other[(idx + 2) % 3] = fix2
            prev = 101.0
            for x in _grid:
                args = list(other)
                args[idx] = x
                b = contract.compute_bhi(*args)
                if b > prev + 1e-9:
                    _check(f"grid monotone non-increasing in {axis}", False,
                           f"computeBhi{tuple(args)}={b} > prev {prev}")
                prev = b
_check("grid sweep monotone non-increasing in cv/vib/load (each alone)", True)
_ref_errs = 0
for cv in _grid:
    for vib in _grid:
        for load in _grid:
            ref = _consumer_compute_bhi(c, cv, vib, load)
            if ref != contract.compute_bhi(cv, vib, load):
                _ref_errs += 1
_check("grid sweep 7x7x7 formula parity (config-block derivation == contract)",
       _ref_errs == 0, f"{_ref_errs} mismatches")
_check("grid clamp (overshoot -> [0,100])",
       contract.compute_bhi(2.0, -1.0, 0.5) == _consumer_compute_bhi(c, 2.0, -1.0, 0.5))

# --- D. ENH-01: MemoryStore bridge-tag isolation + legacy reload --------------
with tempfile.TemporaryDirectory(prefix="vitish-bridge-tag-") as td:
    cache = Path(td) / "state_cache.json"
    st = db.MemoryStore(bridge="z24", cache_path=cache)
    st.insert_accel(node=1, ts=1.0, rms=0.03, flag=0)                       # z24 (default)
    st.insert_accel(node=7, ts=2.0, rms=0.50, flag=1, bridge="live-demo")   # foreign
    st.insert_accel(node=8, ts=3.0, rms=0.60, flag=1, bridge="esp01-1")     # foreign
    st.insert_bhi(ts=1.0, bhi=87.0, u=3.0, cv=0.1, vib=0.12, load=0.19, state="GREEN")
    st.insert_bhi(ts=2.0, bhi=60.0, u=3.0, cv=0.3, vib=0.3, load=0.3, state="AMBER",
                  bridge="live-demo")
    st.insert_alert(ts=1.0, severity="warning", source="fusion", text="z24 alert",
                    recommendation="r", bridge="z24")
    st.insert_alert(ts=2.0, severity="critical", source="live", text="foreign",
                    recommendation="r", bridge="live-demo")
    st.close()

    st2 = db.MemoryStore(bridge="z24", cache_path=cache)  # reload from JSONL
    rows = st2.recent_rms("z24", 10)
    _check("ENH-01 recent_rms('z24') excludes foreign rows",
           len(rows) == 1 and rows[0]["node"] == 1, str(rows))
    rows = st2.recent_rms("live-demo", 10)
    _check("ENH-01 recent_rms('live-demo') returns only its row",
           len(rows) == 1 and rows[0]["node"] == 7, str(rows))
    bhi = st2.recent_bhi("z24", 10)
    _check("ENH-01 recent_bhi('z24') excludes foreign bhi",
           len(bhi) == 1 and bhi[0]["bhi"] == 87.0, str(bhi))
    bhi = st2.recent_bhi("live-demo", 10)
    _check("ENH-01 recent_bhi('live-demo') returns only its row (BUG-01)",
           len(bhi) == 1 and bhi[0]["bhi"] == 60.0, str(bhi))
    al = st2.recent_alerts("z24", 10)
    _check("ENH-01 recent_alerts('z24') excludes foreign alert",
           len(al) == 1 and al[0]["text"] == "z24 alert", str(al))
    cs = st2.current_state("z24")
    _check("ENH-01 current_state('z24') bhi + nodes scoped",
           cs["bhi"] == 87.0 and "1" in cs["nodes"] and "7" not in cs["nodes"],
           f"bhi={cs['bhi']} nodes={sorted(cs['nodes'])}")
    st2.close()  # release the cache file handle before tempdir cleanup (Windows)

# legacy JSONL record (no bridge key) still loads, attributed to the store's bridge
with tempfile.TemporaryDirectory(prefix="vitish-legacy-cache-") as td:
    cache = Path(td) / "state_cache.json"
    cache.write_text(json.dumps({"kind": "accel",
                                 "data": {"ts": 1.0, "node": 9, "rms": 0.04, "flag": 0}}) + "\n",
                     encoding="utf-8")
    st3 = db.MemoryStore(bridge="z24", cache_path=cache)
    rows = st3.recent_rms("z24", 10)
    _check("ENH-01 legacy no-bridge record attributed to store bridge",
           len(rows) == 1 and rows[0]["node"] == 9, str(rows))
    rows = st3.recent_rms("other", 10)
    _check("ENH-01 legacy record not leaked to other bridge", len(rows) == 0, str(rows))
    st3.close()  # release the cache file handle before tempdir cleanup (Windows)

db.reset_store()

print("\nRESULT", "FAIL" if _FAILS else "PASS", len(_FAILS), "failures")
sys.exit(1 if _FAILS else 0)
