# VITISH 2026 · AI-Based Structural Health Monitoring (PS#99)

Prevent the next Morbi. A 36-hour hackathon build: IoT vibration pipeline + computer-vision crack detection + digital twin + predictive maintenance, fused into one auditable Bridge Health Index.

## Stack

| Layer | Tech |
|---|---|
| Edge / sensing | Z24 replay simulator (real benchmark data) + ESP32-S3/ADXL355 (stretch) |
| Communication | MQTT (Mosquitto, local), WebSocket bridge |
| AI | YOLO26s-seg (CV) · VAE+OCSVM + LSTM-AE (vibration) · MiniRocket fallback |
| Fusion | Transparent BHI — 3 sub-indices + uncertainty band |
| Digital twin | React Three Fiber v9 + React 19.2 + three 0.185 + MapLibre |
| Persistence | Postgres (Docker) |

## Quick start

```bash
# 1. infra (Mosquitto MQTT + Postgres)
docker compose up -d --build

# 2. backend + simulator + WS bridge + API
python backend/app/run_all.py

# 3. twin (dev server)
cd twin && npm install && npm run dev
```

See the Obsidian vault (`vault/`) for the full master plan, research, demo script, and Q&A prep.

## Layout

```
backend/   Python pipeline: simulator, MQTT, Postgres, WebSocket bridge, FastAPI
models/    Vibration + CV + fusion (train & inference, with demo fallbacks)
twin/      React Three Fiber digital twin
vault/     Obsidian knowledge base (open this folder in Obsidian)
data/      Dataset cache (gitignored)
```

## 6-minute demo

```bash
cd backend && python app/run_all.py --demo   # simulator + fusion + API + storyboard driver
# open http://localhost:8000/docs · watch the twin at ws://localhost:8765
# timeline: 0s healthy GREEN -> 45s crack -> 75s vibration anomaly -> 110s BHI RED -> 140s copilot -> 175s hold
```
