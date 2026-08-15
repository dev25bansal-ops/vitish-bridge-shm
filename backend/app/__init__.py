"""
VITISH 2026 · PS#99 SHM — backend pipeline package.

Contains the simulator, MQTT plumbing, persistence, WebSocket bridge, FastAPI
API and the 6-minute demo driver.  The authoritative message contract lives in
``app.contract`` and MUST NOT be modified.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# BLAS thread cap (set BEFORE numpy's first BLAS call)
#
# numpy ships with a 24-thread OpenBLAS; for this workload (many tiny 114x114
# FEM eigenvalue solves, one per simulator tick / stiffness snapshot) the
# thread-pool spin-up + barrier sync costs ~0.18 s PER CALL vs ~0.0035 s with a
# single thread — a 50x wall-clock difference that visibly stretched the demo
# cadence (measured 2026-08-15, models/vibration/stiffness.fem_modes).  This
# file runs before any backend module imports numpy, so the env var is in place
# before the first BLAS op.  setdefault: a user's explicit env wins.
# ---------------------------------------------------------------------------
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# ---------------------------------------------------------------------------
# sys.path bootstrap
#
# We want `from app import ...` to work no matter how the code is launched:
#   python backend/app/run_all.py          (from repo root)
#   python app/simulator.py                (from backend/)
#   python -m app.run_all                  (from backend/)
# Importing the `app` package triggers this file, which puts both the backend
# dir and the repo root on sys.path (the repo root is needed so that the
# pluggable ML predictor at models/vibration/demo_predictor.py can be imported
# when the models agent drops it in).
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parent
_ROOT = _BACKEND.parent
for _p in (_BACKEND, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
