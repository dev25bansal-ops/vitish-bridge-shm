---
tags: [overview, components, vitish-2026, shm]
created: 2026-08-13
---

# The 4 Mandated Components

The hackathon requires exactly four components. Each maps to a repo module and a storyboard beat. All four stay demonstrable even on 100% replay ([[36h-Build-Plan]] H32 rule).

| # | Component | Repo module | Build source | Demo beat |
|---|---|---|---|---|
| 1 | **IoT sensors** | `simulator/` + `mqtt/` | Z24 replay simulator (nodes 6–8), ESP32-S3 + ADXL355 stretch goal | 2:00–4:00 LIVE: sensor stream labeled "Z24 · 100 Hz" or "LIVE" |
| 2 | **Computer vision** | `cv/` | YOLO26s-seg binary crack segmenter on SDNET2018 | 2:00–4:00: crack detected → overlay |
| 3 | **Digital twin** | `twin/` | R3F parametric Morbi-style suspension bridge + MapLibre 50-bridge view | 2:00–4:00: twin highlights affected section, BHI 87 → 12 |
| 4 | **Predictive maintenance** | `vibration/` + `fusion/` | VAE+OCSVM / LSTM-AE on temp-compensated features → BHI + copilot advice | 2:00–4:00: anomaly rises; copilot: "load restriction + strain-gauge verification" |

## Data flow (one hero demo path)

`simulator → MQTT (mosquitto) → Postgres + WS bridge → models (cv/vibration) → fusion/BHI → twin + dashboard`

Full detail: [[System-Architecture]] and the frozen [[Message-Contract]].

## Component quality bars (from [[Metrics]])

- CV: measured mAP@0.5 on own 70/20/10 split.
- Vibration: full confusion matrix per Z24 scenario; anomaly = >3σ of healthy envelope.
- Fusion: transparent BHI with 3 sub-indices + uncertainty band ([[BHI-Formula]]).
- Twin: parametric model, offline-safe, no CDN font dependency ([[Digital-Twin]]).

Related: [[Mission]] · [[Key-Decisions]] · [[Storyboard]]
