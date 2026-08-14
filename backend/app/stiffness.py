"""
Stiffness tracker — the Z24 box-girder physics overlay for the twin.

Subscribes to ``bridge/z24/accel`` (same stream fusion consumes), measures the
first vertical-mode frequency f1 as the spectral peak in the 2-8 Hz band,
self-baselines against the first healthy windows, and exposes one honest
snapshot (f1, EI drift, model-inferred damage %, mode shapes) built by
``models.vibration.stiffness``.

This is an *explainability* layer: it never touches the BHI path or the demo
arc.  The arc gate (backend/tests/test_demo_arc.py) pins BHI bands only.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Deque, Dict, Optional

import numpy as np

from app import contract
from app.config import Settings

log = logging.getLogger(__name__)

# Spectral band for the first vertical mode (Z24 f1 ≈ 3.8-4.0 Hz; the heuristic
# floor in app/anomaly uses the same 2-8 Hz band).
_BAND_MIN, _BAND_MAX = 2.0, 8.0
_BASELINE_WINDOWS = 30   # healthy windows averaged into the f1 baseline
_STALE_AFTER_S = 12.0    # snapshot reports stale after this long with no accel


def _peak_f1(samples: np.ndarray, fs: float) -> float:
    """Dominant frequency in the first-mode band (rfft peak)."""
    n = samples.size
    if n < 8:
        return 0.0
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    power = np.abs(np.fft.rfft(samples - np.mean(samples))) ** 2
    band = (freqs >= _BAND_MIN) & (freqs <= _BAND_MAX)
    pb, fb = power[band], freqs[band]
    if not pb.size:
        return 0.0
    return float(fb[np.argmax(pb)])


class StiffnessTracker:
    def __init__(self, cfg: Settings, bus) -> None:
        self.cfg = cfg
        self.bus = bus
        self._rings: Dict[int, Deque[float]] = {
            node: deque(maxlen=cfg.window_n) for node in cfg.nodes
        }
        self._peaks: Deque[float] = deque(maxlen=_BASELINE_WINDOWS)
        self._f1: float = 0.0
        self._baseline: Optional[float] = None
        self._last_seen = 0.0
        self._token: Optional[int] = None
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------------
    def start(self) -> None:
        self._token = self.bus.subscribe(
            f"bridge/{self.cfg.bridge_id}/accel", self.on_accel)
        log.info("stiffness tracker running (band %.0f-%.0f Hz, baseline %d wins)",
                 _BAND_MIN, _BAND_MAX, _BASELINE_WINDOWS)

    def stop(self) -> None:
        if self._token is not None:
            self.bus.unsubscribe(self._token)

    # -- accel path ----------------------------------------------------------------
    def on_accel(self, topic: str, payload: Any) -> None:
        if not isinstance(payload, dict) or not payload.get("samples"):
            return
        node = payload.get("node")
        with self._lock:
            ring = self._rings.setdefault(
                int(node), deque(maxlen=self.cfg.window_n))
            ring.extend(payload["samples"])
            if len(ring) >= self.cfg.window_n:
                f1 = _peak_f1(np.asarray(ring, dtype=float),
                              float(payload.get("fs") or self.cfg.fs))
                if f1 > 0:
                    self._f1 = f1
                    self._last_seen = contract.now()
                    # self-baseline: first _BASELINE_WINDOWS measurements only
                    if self._baseline is None:
                        self._peaks.append(f1)
                        if len(self._peaks) >= _BASELINE_WINDOWS:
                            self._baseline = float(np.mean(self._peaks))
                            log.info("stiffness baseline f1 = %.3f Hz",
                                     self._baseline)

    # -- read ----------------------------------------------------------------------
    def snapshot(self) -> dict:
        from models.vibration import stiffness as physics  # lazy import
        with self._lock:
            f1 = self._f1
            base = self._baseline
            age = contract.now() - self._last_seen if self._last_seen else None
        snap = physics.snapshot(f1, base)
        snap["baseline_locked"] = base is not None
        snap["stale"] = bool(age is not None and age > _STALE_AFTER_S)
        snap["age_s"] = round(age, 1) if age is not None else None
        return snap


# --- module-level singleton (set by run_all, read by api) ----------------------
_tracker: Optional[StiffnessTracker] = None


def set_tracker(t: StiffnessTracker) -> None:
    global _tracker
    _tracker = t


def get_tracker() -> Optional[StiffnessTracker]:
    return _tracker
