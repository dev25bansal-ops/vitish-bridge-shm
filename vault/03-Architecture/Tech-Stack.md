---
tags: [architecture, tech-stack, vitish-2026, shm]
created: 2026-08-13
---

# Tech Stack (exact, verified versions)

## Backend / data (Python 3.10+ venv)

| Package | Role |
|---|---|
| paho-mqtt | MQTT client (publish/subscribe) |
| numpy, scipy, pandas | data + features |
| scikit-learn | OCSVM |
| torch | VAE / LSTM-AE |
| ultralytics | YOLO26 / YOLO11 |
| psycopg2 | Postgres |
| python-dotenv | config |

- Broker: **Mosquitto** (or EMQX in Docker).
- DB: **plain Postgres** in Docker — skip TimescaleDB hypertables (a 36-h demo doesn't need them).
- pyoma2 / PySHM: OMA/modal-math **references only** (cite, not deps).
- FastAPI: the WS→HTTP bridge and endpoints ([[Data-Pipeline]]).

## Digital twin / dashboard (npm — pin EXACTLY these)

```json
dependencies: {
  "react": "^19.2.8", "react-dom": "^19.2.8", "three": "^0.185.1",
  "@react-three/fiber": "^9.7.0", "@react-three/drei": "^10.7.8",
  "zustand": "^5.0.14", "recharts": "^3.10.1", "maplibre-gl": "^6.3.0"
},
devDependencies: {
  "vite": "^8.2.0", "@vitejs/plugin-react": "^6.0.5", "typescript": "~6.0.2",
  "@types/react": "^19.2.18", "@types/react-dom": "^19.2.4",
  "@types/three": "^0.185.4", "@types/node": "^24.13.3"
}
```

## Scaffold

```
npm create vite@latest . -- --template react-ts
npm i <the above pinned deps>
# Node 22 LTS or 24 LTS
```

## Hard rules

- R3F ^9.7.0 with React ^19.2.8 — **never** R3F v10 alpha, **never** R3F v8.
- `@types/three` is **mandatory** (three 0.185 ships zero .d.ts).
- Keep TS on ~6.0.2 — don't jump to 7.x mid-hackathon.
- Render text as HTML/CSS or drei `Html` — **avoid drei `<Text>`** (troika fetches a CDN font → offline hazard).
- **CesiumJS only as an optional, dynamically-imported Geo view** (D2-7) — the ~30 MB chunk loads only when the "Geo view" button opens; the ion token lives in gitignored `twin/.env` and is NEVER committed. **MapLibre 6 remains the default fleet view** — no token, offline-safe.

Related: [[Digital-Twin]] · [[System-Architecture]] · [[Pre-Hackathon-Checklist]]
