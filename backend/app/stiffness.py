"""
Stiffness tracker — the Z24 box-girder physics overlay for the twin.

Subscribes to ``bridge/z24/accel`` (same stream fusion consumes), measures the
first vertical-mode frequency f1, self-baselines against the first healthy
windows, and exposes one honest snapshot (f1, EI drift, model-inferred damage %,
mode shapes) built by ``models.vibration.stiffness``.

Measurement honesty (real Z24 replay, 2026-08-14):
  * f1 is measured from the **mid-span node only** (node 7 — the Z24 deck
    mid-span channel).  The off-midspan channels (6/8) sit on a higher mode at
    ~5.1 Hz and contaminate any multi-node peak merge (measured: a 6.02 Hz
    baseline with a spurious 26% "drift" in the healthy state).
  * The spectral band is [2.5, 5.0] Hz — the fundamental range, which excludes
    the ~5.1 Hz higher mode and the rupture tonal's 8/12 Hz harmonics.
  * The raw peak is median-smoothed over the last 7 windows (real data wanders
    window-to-window) and the baseline is the median of the first 30 peaks.

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
# floor in app/anomaly uses the same 2-8 Hz band).  Narrowed to the fundamental
# so the ~5.1 Hz higher mode on off-midspan channels can never win.
_BAND_MIN, _BAND_MAX = 2.5, 5.0
_REF_NODE = 7            # Z24 deck mid-span channel — first mode max response
_BASELINE_WINDOWS = 30   # healthy peaks medianed into the f1 baseline
_SMOOTH_WINDOWS = 21     # median smoothing (~21 s) — damps transient peaks
_TRACK_GATE = 0.08       # ±8% around baseline: reject transient non-modal peaks
_STALE_AFTER_S = 12.0    # snapshot reports stale after this long with no accel


def _peak_f1(samples: np.ndarray, fs: float) -> float:
    """Dominant frequency in the first-mode band (rfft peak + parabolic
    refinement for sub-bin precision — needed to resolve the small real f1
    drift on the Z24 damage segments)."""
    n = samples.size
    if n < 8:
        return 0.0
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    power = np.abs(np.fft.rfft(samples - np.mean(samples))) ** 2
    band = (freqs >= _BAND_MIN) & (freqs <= _BAND_MAX)
    fb, pb = freqs[band], power[band]
    if not pb.size:
        return 0.0
    k = int(np.argmax(pb))
    # parabolic vertex on log-power over the 3-bin neighbourhood
    if 0 < k < pb.size - 1 and pb[k] > 0:
        y0 = float(np.log(max(pb[k - 1], 1e-30)))
        y1 = float(np.log(max(pb[k], 1e-30)))
        y2 = float(np.log(max(pb[k + 1], 1e-30)))
        denom = y0 - 2.0 * y1 + y2
        if abs(denom) > 1e-12:
            delta = 0.5 * (y0 - y2) / denom  # bins from the peak, in [-0.5, 0.5]
            if abs(delta) <= 1.0:
                return float(fb[k] + delta * (fb[1] - fb[0]))
    return float(fb[k])


class StiffnessTracker:
    def __init__(self, cfg: Settings, bus) -> None:
        self.cfg = cfg
        self.bus = bus
        # only the mid-span node cleanly observes the first vertical mode
        self._ref_node = (_REF_NODE if _REF_NODE in cfg.nodes
                          else sorted(cfg.nodes)[len(cfg.nodes) // 2])
        self._rings: Dict[int, Deque[float]] = {
            node: deque(maxlen=cfg.window_n) for node in cfg.nodes
        }
        self._peaks: Deque[float] = deque(maxlen=_SMOOTH_WINDOWS)
        self._baseline_peaks: Deque[float] = deque(maxlen=_BASELINE_WINDOWS)
        self._f1: float = 0.0
        self._baseline: Optional[float] = None
        self._last_seen = 0.0
        self._token: Optional[int] = None
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------------
    def start(self) -> None:
        self._token = self.bus.subscribe(
            f"bridge/{self.cfg.bridge_id}/accel", self.on_accel)
        log.info("stiffness tracker running (node %d, band %.1f-%.1f Hz, "
                 "baseline %d wins)", self._ref_node,
                 _BAND_MIN, _BAND_MAX, _BASELINE_WINDOWS)

    def stop(self) -> None:
        if self._token is not None:
            self.bus.unsubscribe(self._token)

    # -- accel path ----------------------------------------------------------------
    def on_accel(self, topic: str, payload: Any) -> None:
        if not isinstance(payload, dict) or not payload.get("samples"):
            return
        node = payload.get("node")
        if int(node) != self._ref_node:
            return  # off-midspan channels observe a higher mode, not f1
        with self._lock:
            ring = self._rings.setdefault(
                int(node), deque(maxlen=self.cfg.window_n))
            ring.extend(payload["samples"])
            if len(ring) >= self.cfg.window_n:
                f1 = _peak_f1(np.asarray(ring, dtype=float),
                              float(payload.get("fs") or self.cfg.fs))
                if f1 > 0:
                    self._last_seen = contract.now()
                    # Tracking gate: once the baseline is locked, reject
                    # transient non-modal peaks (traffic bursts) that sit far
                    # from the fundamental — real Z24 drift is a few %, spikes
                    # are 10-25% off.
                    if (self._baseline is not None
                            and not (self._baseline * (1.0 - _TRACK_GATE)
                                     <= f1 <= self._baseline * (1.0 + _TRACK_GATE))):
                        return
                    self._peaks.append(f1)
                    self._f1 = float(np.median(self._peaks))
                    # self-baseline: first _BASELINE_WINDOWS measurements only
                    if self._baseline is None:
                        self._baseline_peaks.append(f1)
                        if len(self._baseline_peaks) >= _BASELINE_WINDOWS:
                            self._baseline = float(np.median(
                                self._baseline_peaks))
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
