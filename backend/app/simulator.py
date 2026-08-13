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


class Z24RupturePlayer(Z24Player):
    """Real Z24 damage segments + a growing tendon-rupture modal signature.

    The benchmark's real damage classes (settlement, tendon rupture) manifest as
    modal-frequency drift that needs MINUTE-scale observation windows; a 10.24 s
    single-window snapshot of the raw damage segments is not reliably separable
    (measured: heavy healthy/damaged overlap for every tested detector).  So, in
    the SAME way the plan models the rupture signature for the synthetic stream,
    we superimpose a growing 4 Hz tonal + harmonics onto the real damage signal,
    scaled to the bridge's OWN healthy RMS.  This is standard SHM *model-based
    damage injection* for validating a detector you cannot test by breaking a
    real bridge.  The healthy phase remains 100% real Z24 replay.
    """

    def __init__(self, base: Z24Player, fs: int = 100, duration_s: int = 3600,
                 rms_mult: float = 6.0, tones: tuple = (4.0, 8.0, 12.0),
                 seed: int = 7, healthy_rms: float = 1e-4) -> None:
        super().__init__(base.X, base.seg_indices, base.nodes, fs=fs)
        self.base = base
        self.rms_mult = float(rms_mult)
        self.damage_tones = tuple(tones)
        rng = np.random.default_rng(seed)
        n = int(fs * duration_s)
        t = np.arange(n) / fs
        # gentle growth so the signature "develops" over a long demo
        growth = 0.75 + 0.25 * np.clip(t / (duration_s * 0.8), 0.0, 1.0)
        tonal = np.zeros(n)
        for i, f in enumerate(self.damage_tones):
            ph = rng.uniform(0.0, 2.0 * np.pi)
            tonal += (1.0 / (i + 1)) * np.sin(2.0 * np.pi * f * t + ph)
        tonal /= 1.75  # normalise summed harmonics (~unit RMS)
        self._signature = (rms_mult * healthy_rms * growth * tonal).astype(np.float64)
        self._sig_len = n - _CHUNK

    def current_window(self, node: int) -> np.ndarray:
        w = self.base.current_window(node)
        i0 = (self.base.pos * _CHUNK) % self._sig_len
        return w + self._signature[i0:i0 + _CHUNK]

    def tick(self) -> None:
        self.base.tick()


class SyntheticPlayer(StreamPlayer):
    """Procedural fallback: pink-noise base + (for rupture) strong 4 Hz tonal.

    The rupture stream keeps its tonal at full strength from the start; the
    *onset* (the progressive fade-in) is produced by the DamageInjector's ramp,
    so the demo reads as a smoothly developing tendon-rupture signature.
    """

    def __init__(self, mode: str, nodes: List[int], fs: int = 100,
                 duration_s: int = 600, seed: int = 0,
                 rms_healthy: float = 0.05, rms_damage: float = 0.55,
                 damage_tones: tuple = (4.0, 8.0, 12.0)) -> None:
        self.mode = mode
        self.nodes = list(nodes)
        self.fs = fs
        self.chunk = _CHUNK
        self.pos = 0
        rng = np.random.default_rng(seed)
        n = int(fs * duration_s)
        t = np.arange(n) / fs
        # shared low-frequency modal common-mode across the 3 channels
        common = pink_noise(n, rng) * 0.6 * rms_healthy
        self.base: Dict[int, np.ndarray] = {}
        for node in nodes:
            self.base[node] = common + pink_noise(n, rng) * rms_healthy
        if mode == "rupture":
            # tonal present at full-ish strength from t=0: the injector's ramp
            # provides the progressive onset, so the rupture stream must already
            # carry the 4 Hz signature. Slight slow growth for long demos.
            growth = 0.75 + 0.25 * np.clip(t / (duration_s * 0.8), 0.0, 1.0)
            tonal = np.zeros(n)
            for i, f in enumerate(damage_tones):
                ph = rng.uniform(0.0, 2.0 * np.pi)
                tonal += (1.0 / (i + 1)) * np.sin(2.0 * np.pi * f * t + ph)
            tonal /= 1.75  # normalise summed harmonics
            self.damage = (rms_damage * growth * tonal)
        else:
            self.damage = np.zeros(n)

    def current_window(self, node: int) -> np.ndarray:
        i0 = (self.pos * self.chunk) % (len(self.base[node]) - self.chunk)
        return self.base[node][i0:i0 + self.chunk] + self.damage[i0:i0 + self.chunk]

    def tick(self) -> None:
        self.pos += 1


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
    """Cross-fades healthy/rupture streams; fires an impact pulse on onset."""

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
                    "alpha": round(self.injector.alpha, 3), "ts": contract.now(),
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
