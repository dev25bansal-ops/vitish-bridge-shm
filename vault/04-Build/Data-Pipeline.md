---
tags: [build, pipeline, mqtt, vitish-2026, shm]
created: 2026-08-13
---

# Data Pipeline — replay simulator first

Layer-1/2 backbone. Zero venue dependence ([[System-Architecture]]).

## Z24 replay simulator (primary, ~150 lines)

- Loads `inputs.npy` / `labels.npy` from the HF mirror ([[Z24-Benchmark]]).
- Publishes **nodes 6–8** (of 27 channels): batched **100-sample JSON**, 1 msg/s/node (~6–8 msgs/s total) on `bridge/{id}/accel`.
- **Damage injector:** switches undamaged → tendon-rupture at a storyboard beat — this is the demo-driver that advances the timeline deterministically.
- Robustness: ~5% amplitude jitter + occasional packet drop.
- 100 Hz is real (Z24's actual rate) — fully supportable.

## Synthetic fallback

- If the .npy is unavailable (shouldn't be, pre-downloaded): procedural accelerations at 100 Hz with a damage envelope + temperature signal.

## MQTT + storage

- Mosquitto broker **local on the demo laptop**.
- **Postgres** (plain, Docker) persists history.
- **Memory fallback:** if Postgres is down, an in-process ring buffer keeps the pipeline alive (one-command Docker Compose per [[Pre-Hackathon-Checklist]]).

## WebSocket bridge + FastAPI

- WS bridge pushes `bridge/{id}/bhi` + `flag` to the twin ([[Digital-Twin]]).
- FastAPI endpoints (for "show me a packet" in [[QandA-Prep]] Q6):
  - `GET /status` — pipeline health, node list, source labels.
  - `GET /stream/{node}/latest` — last payload JSON.
  - `POST /inject/{scenario}` — demo-driver damage injection.

## Edge node (stretch)

- ESP32-S3 + ADXL355: rolling RMS anomaly flag (20 lines) + raw publish. **H8 cut rule** if not streaming ([[36h-Build-Plan]]).

Related: [[Message-Contract]] · [[System-Architecture]] · [[Tech-Stack]] · [[Storyboard]]
