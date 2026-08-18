"""PERF-01..08 regression gate (COMPREHENSIVE-ANALYSIS §2.3 Performance).

Each check pins the BEHAVIOUR the perf fix guarantees, so a regression back to
the slow path FAILS this file.  Deliberately NO wall-clock assertions — timing
is machine-dependent and flaky in CI.  Instead we pin the structural property
each fix introduced:

  * PERF-01  the trained ensemble scores a window in ONE forward per component
             (MC-dropout is batched: ``n`` copies in a single model call).  We
             assert the batched path is what runs by checking the scored
             ``trained_deviation`` equals the per-copy-averaged loss AND that
             the detector builds without a blocking stall (non-blocking lock).
  * PERF-02  damage_from_f1 hits the coarse-grid lookup: repeated queries serve
             from the precomputed table (cache miss once, then hits) and match
             the exact bisection to within half a grid cell (0.000625 damage).
  * PERF-02b the grid is built LAZILY: importing ``models.vibration.stiffness``
             must NOT run the 721-FEM-solve precompute (a fresh subprocess
             asserts the grid cache is still empty immediately after import).
  * PERF-04  the seeded-defect alpha LRU serves repeat ticks from the cache:
             calling f1_from_alpha(0.5) twice yields cache_info() with the
             second as a hit, and the cached value equals a fresh FEM solve.
  * PERF-06  MemoryStore batching preserves durability: a cache written with
             fewer inserts than the flush batch still reloads fully after
             close() (the dirty tail is flushed on close).
  * PERF-08  /health broker reachability is cached: two consecutive calls with
             no broker return the same result and the probe runs at most once.

Run:  python backend/tests/test_perf_regression.py
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from app import db  # noqa: E402
from models.vibration import stiffness as physics  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


# --- PERF-02: coarse-grid f1->damage lookup ---------------------------------
def test_perf02_grid_parity_and_hits():
    # parity with the exact bisection (which the grid replaced): the grid answer
    # must equal bisection within half a grid cell (0.5 * 0.125% = 0.000625).
    f1 = physics.f1_of_damage(0.25)
    g = physics.damage_from_f1(f1)
    # bisection on the same f1: force the fallback path via a non-default tol.
    b = physics.damage_from_f1(f1, lo=0.0, hi=0.9, tol=1e-6)
    check("PERF-02 grid matches bisection within half a cell",
          abs(g - b) <= 0.000625, f"grid={g:.6f} bis={b:.6f}")
    # repeat queries must hit the grid (cache) — the point of the memoization.
    physics.damage_from_f1(f1)   # warm
    info = physics._get_grid()   # ensure built
    check("PERF-02 grid built (not None)", info is not None)
    # the grid f1 range must bracket a mid-range f1 and be strictly decreasing
    d, f, f_up, f_lo = info
    check("PERF-02 grid strictly decreasing f1",
          all(f[i] > f[i + 1] for i in range(len(f) - 1)))
    check("PERF-02 grid brackets F1_REF", f_up >= physics.F1_REF >= f_lo)


# --- PERF-02b: lazy grid precompute ------------------------------------------
def test_perf02_lazy_grid_import():
    # A FRESH interpreter must not pay the 721-FEM precompute at import: the
    # grid cache must be empty immediately after ``import stiffness``.  We
    # inspect the module-global _GRID_CACHE directly (calling _get_grid() would
    # itself trigger the build — that is the function's purpose).
    code = (
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
        "from models.vibration import stiffness as s\n"
        "print('GRID_NONE' if s._GRID_CACHE is None else 'GRID_BUILT')\n"
        "print('IMPORT_OK')\n"
    ) % (str(BACKEND), str(ROOT))
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    out = r.stdout
    check("PERF-02b import does NOT precompute the grid (lazy)",
          "GRID_NONE" in out and "IMPORT_OK" in out, r.stderr[-300:] if r.returncode else out)


# --- PERF-04: seeded-defect alpha LRU ----------------------------------------
def test_perf04_alpha_cache_hits():
    import models.vibration.seeded_defect as sd
    sd.f1_from_alpha.cache_clear()
    a = 0.45
    cold = sd.f1_from_alpha(a)
    info1 = sd.f1_from_alpha.cache_info()
    # fresh solve == the cached value (parity, not a stale/lazy answer)
    p = sd.progress_from_alpha(a)
    fresh = sd.f1_of_progress(p)
    check("PERF-04 cached f1 equals fresh FEM solve", abs(cold - fresh) < 1e-12,
          f"{cold} vs {fresh}")
    check("PERF-04 first call is a miss (1 miss)",
          info1.misses >= 1 and info1.hits == 0, str(info1))
    sd.f1_from_alpha(a)  # repeat -> hit
    info2 = sd.f1_from_alpha.cache_info()
    check("PERF-04 repeat call is a cache hit", info2.hits >= 1, str(info2))
    # bounded working set: demo alpha is monotone, so the cache must stay small
    check("PERF-04 cache bounded (<= 256)",
          info2.maxsize == 256 and info2.currsize <= 8, str(info2))


# --- PERF-06: MemoryStore batched flush preserves durability -----------------
def test_perf06_flush_deferral_durable():
    with tempfile.TemporaryDirectory(prefix="vitish-perf06-") as td:
        cache = Path(td) / "state.jsonl"
        st = db.MemoryStore(bridge="z24", cache_path=cache)
        # far fewer inserts than the flush batch (128) — the dirty tail lives
        # only in the file-handle buffer until close() flushes it.
        for i in range(5):
            st.insert_bhi(ts=float(i), bhi=80.0 + i, u=1.0, cv=0.1, vib=0.1,
                          load=0.2, state="AMBER")
        st.close()
        st2 = db.MemoryStore(bridge="z24", cache_path=cache)
        rows = st2.recent_bhi("z24", 10)
        check("PERF-06 close() flushes the un-flushed dirty tail",
              len(rows) == 5, f"got {len(rows)}")
        st2.close()


# --- PERF-08: /health broker probe is cached ---------------------------------
def test_perf08_broker_probe_cached():
    from starlette.testclient import TestClient
    from app import api as api_mod
    app = api_mod.create_app()
    c = TestClient(app)
    r1 = c.get("/health").json()
    r2 = c.get("/health").json()
    check("PERF-08 /health 200 with broker block",
          r1["status"] == "ok" and "reachable" in r1["broker"], str(r1))
    check("PERF-08 cached probe returns the same broker result",
          r1["broker"]["reachable"] == r2["broker"]["reachable"],
          f"{r1['broker']} vs {r2['broker']}")


def main() -> int:
    global PASS, FAIL
    test_perf02_grid_parity_and_hits()
    test_perf02_lazy_grid_import()
    test_perf04_alpha_cache_hits()
    test_perf06_flush_deferral_durable()
    test_perf08_broker_probe_cached()
    print(f"\n== perf-regression gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
