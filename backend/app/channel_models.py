"""
D1-5 · data-realism manifest + per-channel measurement models.

Every number the twin shows comes from ONE of three honest sources:

  * ``z24-replay``  — real measured Z24 benchmark accelerometer signals
  * ``synthetic``   — procedurally modeled signals (dev fallback, no real data)
  * ``live-demo``   — third-party public-broker MQTT feed (never fused into the
                      z24 BHI)

The manifest answers, for every channel, "what am I actually looking at?" and
"which measurement model produced it?".  Synthetic channels carry the full
documented chain (noise sigma + 1/f colour, anti-alias lowpass, ADC
quantization, sensor bias drift, transient spikes).  Real Z24 replay channels
carry NO synthetic effects — they are presented exactly as measured.

Honesty:
  * The measurement models apply to SYNTHETIC channels only.  Real replay is
    never re-quantized or filtered into a "better" number.
  * The manifest is the single source the provenance UI (D1-6) reads, so a
    viewer can always tell a real measurement from a model.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np

from app import contract
from app.config import Settings

log = logging.getLogger(__name__)

# --- documented synthetic measurement chain ------------------------------------
# A typical MEMS accelerometer + 12-bit ADC on a 100 Hz SHM node.
ADC_BITS = 12
ADC_VREF_MSS2 = 4.0                 # 0..4 m/s² full-scale span
LOWPASS_HZ = 45.0                   # anti-alias corner (Nyquist = fs/2 = 50 Hz)
NOISE_RMS_MSS2 = 0.05               # pink (1/f) floor on a modeled channel
NOISE_COLOR = "pink (1/f)"
DRIFT_RMS_PER_HOUR = 0.002          # slow bias wander (m/s² rms per simulated h)
SPIKES_PER_HOUR = 2.0               # transient impulse rate on a modeled channel
PACKET_DROPOUT_PCT = 0.3            # transport loss (documented; the demo stream
                                    # rides the in-process bus so it is not
                                    # applied to the demo stream itself)


def synthetic_spec(node: int, fs: int = 100) -> dict:
    """The documented measurement chain for one modeled (synthetic) channel."""
    return {
        "node": int(node),
        "source": "synthetic",
        "real": False,
        "sensor": "modeled MEMS accelerometer (procedural)",
        "fs": fs,
        "window_s": contract.WINDOW_S,
        "chain": [
            {"stage": "anti-alias lowpass", "corner_hz": LOWPASS_HZ,
             "note": "4th-order Butterworth, corner below Nyquist"},
            {"stage": "bias drift", "rms_per_sim_hour_mss2": DRIFT_RMS_PER_HOUR,
             "note": "slow sensor-bias wander (sub-0.05 Hz)"},
            {"stage": "transient spikes", "per_hour": SPIKES_PER_HOUR,
             "note": "rare broadband impulse bursts (sensor/mains glitches)"},
            {"stage": "ADC quantization", "bits": ADC_BITS,
             "vref_mss2": ADC_VREF_MSS2,
             "lsb_mss2": round(ADC_VREF_MSS2 / (2 ** ADC_BITS - 1), 6),
             "note": "12-bit uniform mid-tread quantizer"},
        ],
        "noise": {"rms_mss2": NOISE_RMS_MSS2, "color": NOISE_COLOR},
        "transport": {"packet_dropout_pct": PACKET_DROPOUT_PCT,
                      "applied": False,
                      "note": "dropout lives at the MQTT/LoRa layer; the demo "
                              "streams over the in-process bus, so none is "
                              "applied here"},
    }


def _lowpass(x: np.ndarray, fs: int, corner_hz: float) -> np.ndarray:
    """Zero-phase 4th-order Butterworth lowpass (scipy, lazy-imported)."""
    from scipy.signal import butter, sosfiltfilt
    sos = butter(4, corner_hz / (0.5 * fs), btype="low", output="sos")
    return sosfiltfilt(sos, x)


def model_measurement_chain(signal: np.ndarray, node: int, fs: int = 100,
                            duration_s: int = 600, seed: int = 0) -> np.ndarray:
    """Apply the documented synthetic chain to a FULL precomputed signal.

    Order: lowpass -> bias drift -> transient spikes -> ADC quantization.
    Deterministic per (node, seed) so tests can pin the behaviour.  This is
    exactly the chain ``synthetic_spec`` documents, so the manifest is never
    aspirational.
    """
    x = np.asarray(signal, dtype=np.float64)
    if x.size < 4:
        return x
    fs = int(fs)
    rng = np.random.default_rng(seed)

    # 1) anti-alias lowpass
    x = _lowpass(x, fs, LOWPASS_HZ)

    # 2) slow bias drift: a few sub-0.05 Hz sinusoids + a gentle random walk,
    #    scaled so its rms matches DRIFT_RMS_PER_HOUR over the buffer duration
    n = x.size
    t = np.arange(n) / fs
    drift = np.zeros(n)
    for f in (0.008, 0.015, 0.03):
        drift += np.sin(2.0 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
    drift /= 3.0                                          # ~unit rms
    walk = np.cumsum(rng.standard_normal(n)) / np.sqrt(n) * 0.5
    slow = (drift * 0.7 + walk * 0.3)
    slow = slow / (np.std(slow) + 1e-12)
    drift_amp = DRIFT_RMS_PER_HOUR * np.sqrt(duration_s / 3600.0)  # /sim buffer
    x = x + slow * drift_amp

    # 3) transient spikes: Poisson-ish schedule across the duration
    n_hours = duration_s / 3600.0
    n_spikes = int(SPIKES_PER_HOUR * n_hours)
    spike = np.zeros(n)
    if n_spikes > 0:
        for _ in range(n_spikes):
            i0 = int(rng.integers(0, max(n - 1, 1)))
            amp = rng.uniform(4.0, 12.0) * NOISE_RMS_MSS2
            # decaying 2-pole burst (~60 ms)
            for k in range(min(12, n - i0)):
                spike[i0 + k] += amp * np.exp(-k / 3.0) * rng.uniform(-1, 1)
    x = x + spike

    # 4) ADC quantization (mid-tread, 12-bit over VREF)
    q = ADC_VREF_MSS2 / (2.0 ** ADC_BITS - 1)
    x = np.clip(x, -ADC_VREF_MSS2, ADC_VREF_MSS2)
    x = np.round(x / q) * q
    return x


# --- runtime data-source registry ----------------------------------------------
# The simulator records which source is actually streaming (z24-replay |
# synthetic | live-demo); the manifest reflects the LIVE choice, not a guess.
_data_source: str = "synthetic"


def set_data_source(source: str) -> None:
    global _data_source
    if source in ("z24-replay", "synthetic", "live-demo"):
        if source != _data_source:
            _data_source = source
            # item 13: a data-source switch changes the signal character, so the
            # anomaly heuristic's healthy envelope (app.anomaly, process-global
            # _baseline shared across all nodes) must not leak a stale reference
            # across the transition — e.g. a future z24-replay -> synthetic
            # switch would otherwise carry an old healthy RMS/tonality reference
            # and misread the new stream.  Reset here at the single choke point
            # every switch passes through (lazy import: anomaly is numpy-only,
            # no circularity).
            try:
                from app import anomaly as anomaly_mod
                anomaly_mod.reset_anomaly_baseline()
                log.debug("anomaly baseline reset on data-source -> %s", source)
            except Exception as exc:  # pragma: no cover - defensive
                log.debug("anomaly baseline reset skipped (%s)", exc)


def get_data_source() -> str:
    return _data_source


# --- manifest -------------------------------------------------------------------
def channel_entry(cfg: Settings, node: int, data_source: str) -> dict:
    """One channel's honest entry: real measured, or a modeled synthetic."""
    fs = int(cfg.fs)
    if data_source == "synthetic":
        return synthetic_spec(node, fs)
    source = "live-demo" if data_source == "live-demo" else "z24-replay"
    role = ("mid-span (first vertical mode max)" if int(node) == 7
            else "deck edge (higher mode ~5.1 Hz)")
    return {
        "node": int(node),
        "source": source,
        "real": True,
        "sensor": f"accelerometer — {role}",
        "fs": fs,
        "window_s": contract.WINDOW_S,
        "synthetic_chain_applied": False,
        "note": "real measured signal — NO synthetic noise/drift/spikes/ADC "
                "applied (re-presented exactly as recorded)",
    }


def build_manifest(cfg: Settings, data_source: Optional[str] = None,
                   live_active: bool = False,
                   live_status: Optional[dict] = None,
                   edge_status: Optional[dict] = None,
                   site_temp: Optional[dict] = None) -> dict:
    """One self-describing data-realism manifest the UI (D1-6) reads.

    ``site_temp`` (optional, NEW-02) is the honest site-temperature block from
    ``app.site_temperature.get_site_temp`` — measured Open-Meteo when reachable,
    else the simulated seasonal fallback with the matching source label.  Passed
    by the API route (which probes); omitted by direct callers so the pure
    manifest builder never touches the network.
    """
    data_source = data_source or get_data_source()
    if data_source not in ("z24-replay", "synthetic", "live-demo"):
        data_source = "synthetic"
    channels = {str(n): channel_entry(cfg, n, data_source) for n in cfg.nodes}

    datasets = [{
        "name": "Z24 benchmark (first-year progressive damage)",
        "url": contract.Z24_MIRROR,
        "shape": f"{contract.Z24_SHAPE[0]} segments × {contract.Z24_SHAPE[1]} "
                 f"channels × {contract.Z24_SHAPE[2]} samples",
        "note": "real measured signals; healthy phase is 100% this replay",
    }]
    manifest = {
        "bridge": cfg.bridge_id,
        "generated_at": contract.now(),
        "data_source": data_source,
        "data_source_label": {
            "z24-replay": "real Z24 benchmark replay",
            "synthetic": "procedural synthetic (dev fallback — no real data)",
            "live-demo": "third-party public-broker MQTT feed (demo only)",
        }[data_source],
        "channels": channels,
        "synthetic_model": synthetic_spec(cfg.nodes[0], int(cfg.fs)),
        "honesty": {
            "real_channels": [n for n, e in channels.items() if e["real"]],
            "modeled_channels": [n for n, e in channels.items() if not e["real"]],
            "synthetic_effects": ("applied to synthetic channels ONLY"
                                  if data_source == "synthetic"
                                  else "none applied (real replay)"),
            "note": ("A 'real' channel is an unmodified measured signal; a "
                     "'modeled' channel is procedural (noise/drift/spikes/ADC). "
                     "Synthetic effects are NEVER applied to real replay."),
        },
        "live_public_feed": {
            "active": bool(live_active),
            "bridge": "live-demo",
            "note": "third-party demo data — never fused into the z24 BHI",
            "status": live_status or {},
        },
        "edge_node": {
            "bridge": "esp32-1",
            "real_hardware": True,
            "note": "real ESP32 DevKit (ESP32-WROOM-32, WiFi+MQTT) edge node — "
                    "accel is a labeled SELF-TEST/BIST tone (no accelerometer "
                    "attached); RSSI/heap/uptime are real; never fused into the "
                    "z24 BHI",
            "status": edge_status or {},
        },
        "datasets": datasets,
    }
    if site_temp is not None:
        manifest["site_temperature"] = {
            "site": site_temp.get("site", "Koppigen A1 (47.136, 7.578)"),
            "temp_c": site_temp.get("temp_c"),
            "source": site_temp.get("source"),
            "source_label": site_temp.get("source_label"),
            "cached": bool(site_temp.get("cached")),
            "fetched_at": site_temp.get("fetched_at"),
            "note": site_temp.get("note"),
        }
    return manifest
