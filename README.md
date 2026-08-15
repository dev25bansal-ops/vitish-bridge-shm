# VITISH · Structural Health Monitoring that catches the next Morbi before the news does

An end-to-end, **honest-by-design** bridge structural-health system: IoT vibration sensing, computer-vision crack detection, a physics-grounded digital twin, and an auditable **Bridge Health Index (BHI)** — every number on screen traces to real data or a clearly-labeled model assumption.

Built for Smart India Hackathon 2026 (PS#99). Demo-ready: **one command starts the whole story.**

## What's real in this demo

This is not a mockup. The pipeline ingests, fuses, and displays **real benchmark data through the real production path**:

| Channel | What it actually is |
|---|---|
| Vibration | **Real Z24 bridge benchmark replay** (Swiss box girder, 14+30+14 m, 100 Hz) — the canonical progressive-damage dataset in structural-health research |
| CV | **`crack_seg.pt` trained on CrackSeg9k** (real crack-segmentation dataset, CC0) + OpenCV fallback; condition cards from actual detections |
| Live feed | **Live public-broker MQTT ingestion** (third-party demo feed, labeled `live-demo`, never fused into the hero BHI) |
| Physics | Euler-Bernoulli 3-span FEM of the Z24 — damage is a **seeded EI loss** (settlement → cracking → tendon rupture, per the published benchmark), and the *measured* first-mode frequency shifts per the evidence |

**Honesty is a feature, not a caveat:** every data source carries a live on-screen label (LIVE / REPLAY / simulated), a provenance panel shows what is real vs. modeled, temperature is separated from real stiffness loss, and the demo narrative is the seeded Z24 campaign — never a claim about Morbi.

## Verified demo arc (measured, real Z24 replay)

`BHI 87.1 GREEN → 45 s crack → 75 s rupture onset (AMBER) → 105 s RED → holds 33.6 — no flicker`. The seeded tendon-rupture defect slides the measured first-mode frequency 3.8 → 3.23 Hz exactly as the physics model predicts, and the twin highlights the affected span in real time.

## Stack

| Layer | Tech |
|---|---|
| Edge / sensing | Z24 replay simulator (real benchmark data) + ESP32-S3/ADXL355 (stretch) |
| Communication | MQTT (Mosquitto), WebSocket bridge, FastAPI |
| AI | YOLO26s-seg (CV, real training) · VAE+OCSVM + LSTM-AE (vibration) · transparent BHI fusion |
| Digital twin | React Three Fiber · three.js · MapLibre · **Cesium ion georeferenced real-world layer** |
| Persistence | Postgres (Docker) + in-memory store |

## Quick start

```bash
# 1. infra (Mosquitto MQTT + Postgres) — optional; the stack runs memory-only without it
docker compose up -d   # images only (mosquitto + postgres); no build step

# 2. backend + simulator + WS bridge + API + auto demo timeline
cd backend && python app/run_all.py --demo

# 3. twin (dev server) — http://localhost:5173
cd twin && npm install && npm run dev
```

Then open the twin. The `▶ Replay damage arc` button runs the whole story; `Geo view` shows the Z24 site on real Cesium terrain/3D tiles.

## Verification

```bash
bash scripts/verify_gate.sh   # 8 gates, 291 checks — the pre-push merge gate
```

## Layout

```
backend/   Python pipeline: simulator, MQTT, Postgres, WebSocket bridge, FastAPI, demo driver
models/    Vibration + CV + fusion + FEM stiffness/seeded-defect (train & inference)
twin/      React Three Fiber digital twin + Cesium geo layer
vault/     Obsidian knowledge base — research, build log, storyboard, Q&A prep
data/      Dataset cache (gitignored)
scripts/   verify_gate.sh + dataset tooling
```

See `vault/` for the research report, the 36-hour build plan, the 6-minute storyboard, and investor Q&A prep.
