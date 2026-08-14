"""
VITISH 2026 · PS#99 SHM — Z24 replay simulator (REPLAY-FIRST).

Data path
---------
* If ``data/z24/inputs.npy`` + ``labels.npy`` exist (shape ``(1530, 27, 6000)``),
  they are replayed with ``mmap_mode`` so the 992 MB file is never loaded into
  RAM.  Each 60 s segment is sliced into 60 batches of 100 samples; one MQTT
  ``bridge/z24/accel`` message is sent per node (channels 6, 7, 8) per second.
* If the files are MISSING, a synthetic fallback streams healthy 1/f coloured
  noise and a tendon-rupture scenario (growing 4 Hz tonal + harmonics + a
  broadband "snap" on onset) that is indistinguishable in *form* from the real
  feed.  The demo never depends on the 992 MB download.

Damage injector
---------------
``DamageInjector`` cross-fades healthy <-> rupture streams over a smooth ramp
and fires a short broadband impact pulse on rupture onset.  It is controlled by
``control/cmd`` events on the shared event bus (scenario=healthy|rupture), which
the API POST /api/demo/scenario and the demo driver both publish.

CLI:  python app/simulator.py [--scenario healthy|rupture] [--loops N]
                                [--synthetic] [--rate 1.0]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# launch bootstrap (works from repo root or backend/): add backend to sys.path
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import contract  # noqa: E402
from app.config import Settings, setup_logging, settings  # noqa: E402
from app.events import EventBus, get_bus  # noqa: E402
from app.mqtt_client import Publisher, emit  # noqa: E402

log = logging.getLogger(__name__)

_CHUNK = contract.ACCEL_SAMPLES          # 100 samples per MQTT message
_CHUNKS_PER_SEG = contract.Z24_SAMPLES_PER_SEG // _CHUNK   # 60


# ---------------------------------------------------------------------------
# signal sources
# ---------------------------------------------------------------------------
def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f (pink) noise via FFT spectral shaping. Returns zero-mean, unit-RMS."""
    freqs = np.fft.rfftfreq(n)
    amps = np.empty(len(freqs))
    amps[0] = 0.0
    amps[1:] = 1.0 / np.sqrt(np.maximum(freqs[1:], 1e-9))
    spec = rng.standard_normal(len(freqs)) + 1j * rng.standard_normal(len(freqs))
    spec[0] = 0.0
    x = np.fft.irfft(spec * amps, n)
    return x / (np.std(x) + 1e-12)


class StreamPlayer:
    """Yield one 100-sample window per node per tick. Subclasses are stateful."""

    def current_window(self, node: int) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def tick(self) -> None:  # pragma: no cover
        raise NotImplementedError


class SyntheticPinkBase(StreamPlayer):
    """Pink-noise deck response + (healthy) ambient first-mode resonance.

    The healthy synthetic stream carries a modest modal resonance at the Z24
    fundamental (``physics.F1_REF`` = 3.80 Hz) on the mid-span node, so the
    stiffness tracker's self-baseline locks near the REAL healthy f1 on the
    synthetic path too — the D2-12 physics overlay (f1, EI drift, seeded
    defect) then reads the same numbers with or without the Z24 download.
    """

    def __init__(self, nodes: List[int], fs: int = 100, duration_s: int = 600,
                 seed: int = 0, rms_healthy: float = 0.05,
                 ambient_f1: float = 0.0, ambient_amp: float = 0.0) -> None:
        self.nodes = list(nodes)
        self.fs = fs
        self.chunk = _CHUNK
        self.pos = 0
        rng = np.random.default_rng(seed)
        n = int(fs * duration_s)
        t = np.arange(n) / fs
        common = pink_noise(n, rng) * 0.6 * rms_healthy
        self.signal: Dict[int, np.ndarray] = {}
        for node in nodes:
            base = common + pink_noise(n, rng) * rms_healthy
            if ambient_f1 > 0 and ambient_amp > 0:
                # standing first-mode response at the Z24 fundamental — strongest
                # at mid-span (node 7), ~0 at the supports (nodes 6/8), matching
                # the FEM mode shape.  Amplitude modest: an ambient deck hum,
                # not damage.
                wgt = 1.0 if node == 7 else 0.0
                ph = rng.uniform(0.0, 2.0 * np.pi)
                res = (np.sin(2.0 * np.pi * ambient_f1 * t + ph)
                       + 0.5 * np.sin(4.0 * np.pi * ambient_f1 * t + 2.0 * ph))
                res /= 1.12
                base = base + ambient_amp * wgt * res
            self.signal[node] = base

    def current_window(self, node: int) -> np.ndarray:
        i0 = (self.pos * self.chunk) % (len(self.signal[node]) - self.chunk)
        return self.signal[node][i0:i0 + self.chunk]

    def tick(self) -> None:
        self.pos += 1


class ModalResonancePlayer(StreamPlayer):
    """Healthy base + a modal resonance at a (possibly time-varying) f1.

    The D2-12 damage signature: a standing-wave response at the FEM first-mode
    frequency of the CURRENT seeded-defect set (``f1_provider()`` Hz), with
    harmonics at 2f/3f (1/k amplitude) and a phase accumulator so f1 can SLIDE
    as the defect progresses — a softening structure, not a forced tone.  The
    resonance is applied to every node (the standing wave is a whole-deck
    response), which also keeps the always-on spectral-heuristic arc intact
    (fusion averages the per-node anomaly scores).

    ``f1_provider`` defaults to the FULLY-seeded Z24 f1 so standalone use (e.g.
    the arc regression test) exercises the deepest defect.
    """

    def __init__(self, base: StreamPlayer, amp: float, fs: int = 100,
                 seed: int = 7, harmonics: tuple = (1.0, 2.0, 3.0),
                 f1_provider=None) -> None:
        self.base = base
        self.amp = float(amp)
        self.fs = fs
        self.harmonics = tuple(harmonics)
        from models.vibration import seeded_defect as _sd
        full = _sd.progress_from_alpha(1.0)
        self.f1_provider = (f1_provider if f1_provider is not None
                            else (lambda f=full: _sd.f1_of_progress(f)))
        rng = np.random.default_rng(seed)
        self._phase: Dict[int, float] = {node: rng.uniform(0.0, 2.0 * np.pi)
                                         for node in getattr(base, "nodes", [])}

    def current_window(self, node: int) -> np.ndarray:
        w = self.base.current_window(node)
        n = w.size
        f1 = float(max(self.f1_provider(), 1.0))
        t = np.arange(n) / self.fs + self._phase.setdefault(node, 0.0)
        sig = np.zeros(n)
        for i, h in enumerate(self.harmonics):
            sig += (1.0 / (i + 1)) * np.sin(2.0 * np.pi * h * f1 * t)
        sig /= 1.75  # normalise summed harmonics (~unit RMS)
        self._phase[node] = self._phase.get(node, 0.0) + n / float(self.fs)
        return w + self.amp * sig

    def tick(self) -> None:
        self.base.tick()


class Z24Player(StreamPlayer):
    """Replay real benchmark segments (healthy or damage label subsets)."""

    def __init__(self, X: np.ndarray, seg_indices: List[int], nodes: List[int],
                 fs: int = 100) -> None:
        self.X = X
        self.seg_indices = [int(i) for i in seg_indices]
        self.nodes = list(nodes)
        self.fs = fs
        self.pos = 0

    def current_window(self, node: int) -> np.ndarray:
        seg = self.seg_indices[(self.pos // _CHUNKS_PER_SEG) % len(self.seg_indices)]
        off = (self.pos % _CHUNKS_PER_SEG) * _CHUNK
        w = self.X[seg, node, off:off + _CHUNK]
        return np.asarray(w, dtype=np.float64)

    def tick(self) -> None:
        self.pos += 1


def _median_healthy_rms(X: np.ndarray, healthy_segs: List[int], nodes: List[int],
                        fs: int = 100, n: int = 8) -> float:
    """Median RMS of a few real healthy windows — the scale reference for the
    superimposed rupture signature (model-based damage injection)."""
    vals: List[float] = []
    for seg in healthy_segs[:n]:
        for node in nodes:
            w = np.asarray(X[seg, node, 0:1024], dtype=np.float64)
            vals.append(float(np.sqrt(np.mean(w ** 2))))
    return float(np.median(vals)) + 1e-12


class Z24RupturePlayer(ModalResonancePlayer):
    """Real Z24 damage segments + a modal resonance at the FEM-seeded f1.

    The benchmark's real damage classes (settlement, tendon rupture) manifest as
    modal-frequency drift that needs MINUTE-scale observation windows; a 10.24 s
    single-window snapshot of the raw damage segments is not reliably separable
    (measured: heavy healthy/damaged overlap for every tested detector).  So, in
    the SAME way the plan models the damage signature for the synthetic stream,
    we superimpose a modal resonance at the seeded-defect f1 (D2-12) onto the
    real damage signal, scaled to the bridge's OWN healthy RMS.  This is
    standard SHM *model-based damage injection* for validating a detector you
    cannot test by breaking a real bridge.  The healthy phase remains 100% real
    Z24 replay.
    """

    def __init__(self, base: Z24Player, fs: int = 100, duration_s: int = 3600,
                 rms_mult: float = 6.0, seed: int = 7,
                 healthy_rms: float = 1e-4) -> None:
        super().__init__(base, amp=rms_mult * float(healthy_rms), fs=fs, seed=seed)


class SyntheticPlayer:
    """Procedural fallback stream (healthy or seeded-defect rupture).

    * healthy  : pink-noise base + ambient first-mode resonance at 3.80 Hz
                 (see SyntheticPinkBase) — the synthetic path's f1 self-baseline
                 locks near the real Z24 healthy fundamental.
    * rupture  : pink-noise base + a strong modal resonance at the FEM f1 of the
                 seeded Z24 defect set (D2-12).  The onset (progressive EI loss
                 -> f1 slide) is produced by the DamageInjector's ramp, so the
                 demo reads as a smoothly developing seeded defect, not a forced
                 tone.

    Each modeled channel is then passed through the DOCUMENTED synthetic
    measurement chain (D1-5): anti-alias lowpass -> bias drift -> transient
    spikes -> ADC quantization.  The manifest (``app/channel_models``) describes
    exactly this chain, so the synthetic stream's realism parameters are never
    aspirational.
    """

    def __init__(self, mode: str, nodes: List[int], fs: int = 100,
                 duration_s: int = 600, seed: int = 0,
                 rms_healthy: float = 0.05, rms_damage: float = 0.55) -> None:
        self.mode = mode
        self.nodes = list(nodes)
        self.fs = fs
        self.chunk = _CHUNK
        self.pos = 0
        from app import channel_models as cm
        if mode == "rupture":
            base = SyntheticPinkBase(nodes, fs=fs, duration_s=duration_s,
                                     seed=seed, rms_healthy=rms_healthy)
            base.signal = {n: cm.model_measurement_chain(
                base.signal[n], n, fs=fs, duration_s=duration_s,
                seed=seed * 100 + int(n)) for n in nodes}
            self.player = ModalResonancePlayer(base, amp=rms_damage, fs=fs,
                                               seed=seed + 3)
        else:
            base = SyntheticPinkBase(nodes, fs=fs, duration_s=duration_s,
                                     seed=seed, rms_healthy=rms_healthy,
                                     ambient_f1=3.80, ambient_amp=0.30 * rms_healthy)
            base.signal = {n: cm.model_measurement_chain(
                base.signal[n], n, fs=fs, duration_s=duration_s,
                seed=seed * 100 + int(n)) for n in nodes}
            self.player = base

    def current_window(self, node: int) -> np.ndarray:
        return self.player.current_window(node)

    def tick(self) -> None:
        self.player.tick()

    @property
    def f1_provider(self):
        return self.player.f1_provider

    @f1_provider.setter
    def f1_provider(self, fn) -> None:
        self.player.f1_provider = fn


def load_z24(data_dir: Path) -> tuple:
    """Return (X, labels) or (None, None) when real data is unusable."""
    inp = data_dir / "inputs.npy"
    lab = data_dir / "labels.npy"
    if not inp.exists() or not lab.exists():
        return None, None
    try:
        X = np.load(str(inp), mmap_mode="r")
        y = np.load(str(lab))
        ok_shape = X.ndim == 3 and X.shape[1] >= 9 and X.shape[2] >= contract.Z24_SAMPLES_PER_SEG
        if not ok_shape or y.shape[0] != X.shape[0]:
            log.warning("Z24 files present but unexpected shape %s / labels %s -> synthetic",
                        X.shape, y.shape)
            return None, None
        return X, y
    except Exception as exc:
        log.warning("could not load Z24 data (%s) -> synthetic", exc)
        return None, None


# ---------------------------------------------------------------------------
# damage injector
# ---------------------------------------------------------------------------
class DamageInjector:
    """Cross-fades healthy/rupture streams; fires an impact pulse on onset.

    D2-12: the "rupture" stream carries a modal resonance at the FEM first-mode
    frequency of the CURRENT seeded-defect set (Z24 progressive damage:
    settlement -> cracking -> tendon rupture), so as the cross-fade alpha ramps
    0->1 the measured f1 slides 3.80 -> ~3.2 Hz per the physics.  ``alpha`` is
    the single source of truth for both the mix ratio AND the defect severity.
    """

    def __init__(self, healthy: StreamPlayer, rupture: StreamPlayer, cfg: Settings,
                 bus: Optional[EventBus] = None, rng_seed: int = 7) -> None:
        self.healthy = healthy
        self.rupture = rupture
        self.cfg = cfg
        self.bus = bus
        self.scenario = "healthy"
        self.switch_t: Optional[float] = None
        self.impact_t0: Optional[float] = None
        self._impact_rng = np.random.default_rng(rng_seed)
        self._rms_ema: Optional[float] = None
        self.alpha = 0.0
        from models.vibration import seeded_defect as _sd
        self._sd = _sd
        # wire the rupture player's f1 to THIS injector's current defect state
        self._wire_f1_provider()

    def _wire_f1_provider(self) -> None:
        inj = self

        def _f1_now() -> float:
            p = inj._sd.progress_from_alpha(inj.alpha)
            return inj._sd.f1_of_progress(p)

        prov = getattr(self.rupture, "f1_provider", None)
        if callable(prov):
            self.rupture.f1_provider = _f1_now

    def set_scenario(self, name: str) -> bool:
        name = str(name).strip().lower()
        if name not in ("healthy", "rupture"):
            raise ValueError(f"unknown scenario {name!r}; expected healthy|rupture")
        if name == self.scenario:
            return False
        self.scenario = name
        self.switch_t = time.monotonic()
        if name == "rupture":
            self.impact_t0 = time.monotonic()
        log.info("DAMAGE INJECTOR: scenario -> %s (ramp %.1f s)", name, self.cfg.ramp_s)
        if self.bus is not None:
            self.bus.publish("control/status",
                             {"cmd": "scenario", "scenario": name, "ts": contract.now()})
        return True

    def _alpha_now(self) -> float:
        if self.switch_t is None:
            return 1.0 if self.scenario == "rupture" else 0.0
        frac = (time.monotonic() - self.switch_t) / max(self.cfg.ramp_s, 0.1)
        if self.scenario == "rupture":
            return float(np.clip(frac, 0.0, 1.0))
        return float(np.clip(1.0 - frac, 0.0, 1.0))

    def seeded_state(self) -> dict:
        """Current D2-12 seeded-defect narrative (progress, f1, EI loss, source)."""
        p = self._sd.progress_from_alpha(self.alpha)
        return self._sd.describe(p, f1_base=self._sd.overview()["f1_ref"])

    def current_window(self, node: int) -> np.ndarray:
        self.alpha = self._alpha_now()
        hw = self.healthy.current_window(node)
        rw = self.rupture.current_window(node)
        win = (1.0 - self.alpha) * hw + self.alpha * rw
        if self.impact_t0 is not None:
            dt = time.monotonic() - self.impact_t0
            if dt < self.cfg.impact_s:
                env = self.cfg.impact_amp * np.exp(-3.0 * dt / max(self.cfg.impact_s, 0.1))
                win = win + env * self._impact_rng.standard_normal(len(win))
            else:
                self.impact_t0 = None
        return win

    def tick(self) -> None:
        self.healthy.tick()
        self.rupture.tick()

    def rms_flag(self, rms: float) -> int:
        """Device-style runaway flag: fires when rms >> rolling healthy baseline."""
        if self._rms_ema is None:
            self._rms_ema = float(rms)
            return 0
        thr = max(self._rms_ema * self.cfg.accel_flag_factor, self.cfg.accel_flag_floor)
        flagged = int(rms > thr)
        if not flagged:
            self._rms_ema = 0.9 * self._rms_ema + 0.1 * float(rms)
        return flagged


# ---------------------------------------------------------------------------
# simulator
# ---------------------------------------------------------------------------
class Simulator:
    def __init__(self, cfg: Settings, publisher: Publisher,
                 bus: Optional[EventBus] = None, synthetic: bool = False,
                 scenario: str = "healthy", loops: int = 0, rate: float = 1.0) -> None:
        self.cfg = cfg
        self.publisher = publisher
        self.bus = bus
        self.synthetic = synthetic
        self.scenario = scenario
        self.loops = int(loops)          # number of 60 s segments; 0 = infinite
        self.rate = float(rate)
        self._stop = threading.Event()

        self.data_source = "synthetic"
        self.players: Dict[str, StreamPlayer] = {}
        self._build_players()
        from app import channel_models as cm
        cm.set_data_source(self.data_source)

        self.injector = DamageInjector(self.players["healthy"], self.players["rupture"],
                                       cfg, bus)
        self.injector.set_scenario(scenario)
        self._control_token: Optional[int] = None
        if bus is not None:
            self._control_token = bus.subscribe("control/cmd", self._on_control)

    # -- wiring -----------------------------------------------------------------
    def _build_players(self) -> None:
        X, y = (None, None)
        if not self.synthetic:
            X, y = load_z24(self.cfg.data_dir)
        nodes = self.cfg.nodes
        if X is None:
            self.data_source = "synthetic"
            log.info("using SYNTHETIC fallback stream")
            self.players = {
                "healthy": SyntheticPlayer("healthy", nodes, seed=1),
                "rupture": SyntheticPlayer("rupture", nodes, seed=2),
            }
            return

        labels = np.asarray(y, dtype=int).ravel()
        # row indices (positions in X) whose label falls in the desired class.
        healthy = [int(i) for i in np.where(np.isin(labels, contract.Z24_HEALTHY_LABELS))[0]]
        damage_mask = np.isin(labels, list(range(10, 17)))  # tendon-rupture first
        if not damage_mask.any():
            damage_mask = np.isin(labels, contract.Z24_DAMAGE_LABELS)
        damage = [int(i) for i in np.where(damage_mask)[0]]
        if not healthy or not damage:
            log.warning("Z24 labels lack healthy/damage classes -> synthetic")
            self.data_source = "synthetic"
            self.players = {
                "healthy": SyntheticPlayer("healthy", nodes, seed=1),
                "rupture": SyntheticPlayer("rupture", nodes, seed=2),
            }
            return

        self.data_source = "z24-replay"
        log.info("replaying REAL Z24 benchmark (healthy=%d segs, damage=%d segs)",
                 len(healthy), len(damage))
        healthy_rms = _median_healthy_rms(X, healthy, nodes)
        log.info("Z24 healthy RMS reference: %.2e -> rupture signature %.2e (%.1fx)",
                 healthy_rms, 6.0 * healthy_rms, 6.0)
        self.players = {
            "healthy": Z24Player(X, healthy, nodes),
            "rupture": Z24RupturePlayer(Z24Player(X, damage, nodes),
                                        healthy_rms=healthy_rms),
        }

    def _on_control(self, topic: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("cmd") == "scenario":
            try:
                self.injector.set_scenario(payload.get("scenario", "healthy"))
            except ValueError as exc:
                log.warning("ignored control: %s", exc)

    def seeded_state(self) -> dict:
        """Current D2-12 seeded-defect narrative (for the REST endpoint)."""
        return self.injector.seeded_state()

    # -- run loop -----------------------------------------------------------------
    def run(self) -> None:
        if not self.publisher.wait_connected(timeout=3.0):
            log.warning("MQTT broker not reachable — streaming over the event bus only")
        tick = 0
        seg = 0
        while not self._stop.is_set():
            ts = contract.now()
            for node in self.cfg.nodes:
                win = self.injector.current_window(node)
                rms = float(np.sqrt(np.mean(win ** 2)))
                flag = self.injector.rms_flag(rms)
                topic = contract.TOPIC_ACCEL.format(bridge=self.cfg.bridge_id)
                payload = {
                    "bridge": self.cfg.bridge_id,
                    "node": int(node),
                    "ts": round(ts, 3),
                    "fs": self.cfg.fs,
                    "samples": [round(float(x), 6) for x in win],
                    "rms": round(rms, 6),
                    "flag": flag,
                    "msg_id": f"sim-{tick}-{node}",
                }
                emit(topic, payload, self.publisher, bus=self.bus,
                     qos=contract.QOS_TELEMETRY)

            # node heartbeat every 10 s
            if tick % 10 == 0:
                self.publisher.publish_status(node=self.cfg.nodes[0],
                                              online=True,
                                              rssi=-62 + (tick // 10) % 5)
            # damage-level control/status for the twin (1/s)
            if self.bus is not None:
                self.bus.publish("control/status", {
                    "cmd": "alpha", "scenario": self.injector.scenario,
                    "alpha": round(self.injector.alpha, 3),
                    # D2-12 seeded-defect narrative (progress, FEM f1, EI loss)
                    "seeded": self.injector.seeded_state(),
                    "ts": contract.now(),
                })

            self.injector.tick()
            tick += 1
            seg = tick // _CHUNKS_PER_SEG
            if self.loops and seg >= self.loops:
                log.info("simulator finished (%d segments)", self.loops)
                break
            self._stop.wait(1.0 / self.rate)

    def stop(self) -> None:
        self._stop.set()
        if self.bus is not None and self._control_token is not None:
            self.bus.unsubscribe(self._control_token)


# --- module-level singleton (set by run_all, read by api) --------------------
_simulator: Optional[Simulator] = None


def set_simulator(s: "Simulator") -> None:
    global _simulator
    _simulator = s


def get_simulator() -> Optional["Simulator"]:
    return _simulator


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="VITISH SHM Z24 replay simulator")
    parser.add_argument("--scenario", choices=["healthy", "rupture"], default="healthy",
                        help="starting scenario")
    parser.add_argument("--loops", type=int, default=0,
                        help="number of 60 s segments to replay (0 = infinite)")
    parser.add_argument("--synthetic", action="store_true",
                        help="force the synthetic fallback stream")
    parser.add_argument("--rate", type=float, default=1.0,
                        help="playback speed multiplier (1.0 = real time)")
    parser.add_argument("--no-broker", action="store_true",
                        help="skip MQTT entirely; stream only on the event bus")
    args = parser.parse_args(argv)

    setup_logging()
    cfg = settings
    bus = get_bus()
    publisher = Publisher(cfg)
    publisher.start()

    sim = Simulator(cfg, publisher, bus=bus, synthetic=args.synthetic,
                    scenario=args.scenario, loops=args.loops, rate=args.rate)
    log.info("simulator data source: %s", sim.data_source)
    log.info("publishing accel on %s every ~1s per node %s",
             cfg.accel_topic(), cfg.nodes)
    try:
        sim.run()
    except KeyboardInterrupt:
        print("\nsimulator stopped (Ctrl-C)")
    finally:
        sim.stop()
        publisher.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
