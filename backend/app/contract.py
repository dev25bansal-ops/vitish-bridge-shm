"""
VITISH 2026 · PS#99 SHM — authoritative message contract & shared schema.

FROZEN on 13 Aug 2026. Every component (simulator, backend, ML, twin) MUST
conform to these topic names, payload shapes, and the BHI formula. If you
change this file, you change the integration contract — coordinate first.

Message flow (replay-first, live-second):
  simulator ──MQTT──► backend (subscribe) ──► Postgres
                                    ├─► inference (VAE/OCSVM, LSTM-AE) ──► BHI
                                    └─► WebSocket bridge ──► digital twin
"""
from __future__ import annotations

import time
from typing import Any, Literal

# ---------------------------------------------------------------------------
# MQTT topics
# ---------------------------------------------------------------------------
BRIDGE_ID = "z24"  # hero bridge; demo uses this id end-to-end

# One batched 100-sample payload per node per second
TOPIC_ACCEL = "bridge/{bridge}/accel"
# One 256x256 JPEG frame per published image (CV branch)
TOPIC_FRAME = "bridge/{bridge}/frame"
# BHI fused health index, ~1 msg/s
TOPIC_BHI = "bridge/{bridge}/bhi"
# Anomaly alert / state-change events (QoS 1 telemetry, alarms elevated)
TOPIC_ALERT = "bridge/{bridge}/alert"
# Node online/offline heartbeat + metadata
TOPIC_STATUS = "bridge/{bridge}/status"
# Simulated LoRa backhaul label (production backhaul; demo streams over MQTT/WiFi)
TOPIC_LORA = "bridge/{bridge}/rf"

# QoS: telemetry = 1, alarms = 2 (picked ONE scheme; do not mix in the demo)
QOS_TELEMETRY = 1
QOS_ALARM = 2

# ---------------------------------------------------------------------------
# Payload schemas (JSON)
# ---------------------------------------------------------------------------
# bridge/{id}/accel:
#   { "bridge": "z24", "node": 7, "ts": 1786.5, "fs": 100,
#     "samples": [100 floats, m/s^2], "rms": 0.083, "flag": 0 }
#   - samples: exactly FS_ACCEL floats, windowed 1 s of data
#   - rms: rolling RMS on the window
#   - flag: 0 = healthy, 1 = edge RMS anomaly flag (computed on device if present)
ACCEL_SAMPLES = 100

# bridge/{id}/bhi:
#   { "bridge": "z24", "ts": ..., "bhi": 82.4, "u": 3.1,
#     "cv": 0.35, "vib": 0.12, "load": 0.40, "state": "GREEN" }
#   - bhi: 0-100 headline metric
#   - u:   uncertainty interval (+/-) around bhi (MC-dropout/ensemble spread)
#   - cv/vib/load: sub-indices in [0,1] (evidence, higher = worse)
#   - state: GREEN >= 70, AMBER in [50,70), RED < 50

# bridge/{id}/frame:
#   { "bridge": "z24", "ts": ..., "cam": "webcam"|"pi-zero"|"dataset",
#     "image_b64": "...", "detections": [ { "cls": "crack", "conf": 0.87,
#       "mask_rle": "...", "box": [x,y,w,h] } ] }

# bridge/{id}/alert:
#   { "bridge": "z24", "ts": ..., "severity": "info"|"warning"|"critical",
#     "source": "cv"|"vib"|"load"|"fusion", "text": "...",
#     "recommendation": "..." }

# bridge/{id}/status:
#   { "bridge": "z24", "node": 7, "ts": ..., "online": true,
#     "firmware": "vitish-edge-0.1", "rssi": -62 }

# ---------------------------------------------------------------------------
# Sampling & windows
# ---------------------------------------------------------------------------
FS_ACCEL = 100                 # Hz (matches Z24 benchmark)
WINDOW_S = 10.24               # inference window length in seconds
WINDOW_N = int(FS_ACCEL * WINDOW_S)   # 1024 samples per anomaly inference
ANOMALY_LATENCY_S = WINDOW_S + 0.5    # window + inference overhead (honest claim)

# ---------------------------------------------------------------------------
# BHI — transparent, auditable 3-sub-index fusion.
# BHI = 100 * (1 - w_cv*cv - w_vib*vib - w_load*load) * age_factor * traffic_factor
# Weights are a DESIGN choice reflecting evidence reliability, to be
# re-calibrated on pilot data (NOT "swept to maximize F1" — Z24 has no images).
# ---------------------------------------------------------------------------
BHI_W = {"cv": 0.40, "vib": 0.35, "load": 0.25}
BHI_GREEN = 70.0
BHI_AMBER = 50.0
AGE_FACTOR = 1.0        # demo: 1.0 (age model added on pilot data)
TRAFFIC_FACTOR = 1.0    # demo: 1.0

HealthState = Literal["GREEN", "AMBER", "RED"]


def state_for(bhi: float) -> HealthState:
    if bhi >= BHI_GREEN:
        return "GREEN"
    if bhi >= BHI_AMBER:
        return "AMBER"
    return "RED"


def compute_bhi(
    cv: float,
    vib: float,
    load: float,
    w: dict[str, float] | None = None,
    age_factor: float = AGE_FACTOR,
    traffic_factor: float = TRAFFIC_FACTOR,
) -> float:
    """Deterministic, auditable BHI. Sub-indices clamped to [0,1]."""
    w = w or BHI_W
    cv = max(0.0, min(1.0, cv))
    vib = max(0.0, min(1.0, vib))
    load = max(0.0, min(1.0, load))
    penalty = w["cv"] * cv + w["vib"] * vib + w["load"] * load
    bhi = 100.0 * (1.0 - penalty) * age_factor * traffic_factor
    return round(max(0.0, min(100.0, bhi)), 1)


def now() -> float:
    """Wall-clock epoch seconds. Inject this for replay determinism."""
    return time.time()


# ---------------------------------------------------------------------------
# Z24 benchmark metadata (from the processed HuggingFace mirror)
# ---------------------------------------------------------------------------
Z24_MIRROR = "https://huggingface.co/datasets/thanglexuan/Z24-dataset-processed"
Z24_SHAPE = (1530, 27, 6000)   # inputs.npy: (segments, channels, samples)
Z24_SAMPLES_PER_SEG = 6000     # 60 s @ 100 Hz per segment
Z24_CHANNELS = 27
Z24_SIM_NODES = [6, 7, 8]      # channels we publish (index into axis 1)

# 17 progressive-damage scenarios (labels) of the Z24 benchmark.
# NOTE: identify the healthy reference classes (0 and ~6) before training —
# the anomaly detector is trained on healthy windows only.
Z24_SCENARIOS = {
    0: "healthy",
    1: "healthy (reference)",
    2: "pier settlement 20 mm",
    3: "pier settlement 40 mm",
    4: "pier settlement 80 mm",
    5: "pier settlement 95 mm",
    6: "healthy (reference)",
    7: "concrete spalling",
    8: "hinge failure",
    9: "anchor-head failure",
    10: "tendon rupture (1)",
    11: "tendon rupture (2)",
    12: "tendon rupture (3)",
    13: "tendon rupture (4)",
    14: "tendon rupture (5)",
    15: "tendon rupture (6)",
    16: "tendon rupture (7)",
}
Z24_HEALTHY_LABELS = [0, 1, 6]
Z24_DAMAGE_LABELS = [l for l in Z24_SCENARIOS if l not in Z24_HEALTHY_LABELS]

# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------
def validate_accel(payload: dict[str, Any]) -> list[str]:
    errors = []
    if payload.get("bridge") != BRIDGE_ID:
        errors.append(f"bridge must be '{BRIDGE_ID}'")
    if payload.get("fs") != FS_ACCEL:
        errors.append(f"fs must be {FS_ACCEL}")
    samples = payload.get("samples")
    if not isinstance(samples, list) or len(samples) != ACCEL_SAMPLES:
        errors.append(f"samples must be list of {ACCEL_SAMPLES} floats")
    return errors
