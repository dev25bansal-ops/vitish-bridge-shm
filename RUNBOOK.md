# VITISH SHM — Demo RUNBOOK

Operate, recover, and rehearse the PS#99 structural-health demo. Every command is
run from a **Git Bash** terminal (this repo) unless stated otherwise.

> Guardrail: **the pinned demo arc (GREEN 87.1 → AMBER 67.5 → RED 33.6) must
> never break.** After ANY change run `bash scripts/verify_gate.sh` — it must
> end with `== ALL 15 GATES PASS ==`.

---

## 1. Cold start (the whole stack in 2 terminals)

```bash
# Terminal 1 — backend (simulator + MQTT subscriber + fusion + WS + API + demo driver)
cd backend
python -m app.run_all --demo
```

```bash
# Terminal 2 — digital twin frontend
cd twin
npm run dev
```

Open **http://localhost:5173** → the twin renders the Z24 hero bridge and drives
the full healthy→rupture→recovery story. Backend banner prints the actual API /
WS ports (they fall back to the next free port if 8000/8765 are busy).

Add `--live` (or `VITISH_LIVE=1`) to also stream the **real public MQTT feed**
(`test.mosquitto.org`, bridge `live-demo`) alongside the Z24 replay:

```bash
cd backend
python -m app.run_all --demo --live
```

`--speed 3.4` runs the 175 s demo ~3× faster; `--rate 3.4` runs the simulator
faster (the ~51 s detector warm-up then completes in ~15 s).

---

## 2. Network-off start order (venue WiFi is unreliable)

The only external-network dependency is the optional live public-MQTT feed. The
core demo is 100% local. Start order with **no internet**:

1. **Backend** — `cd backend && python -m app.run_all --demo` (NO `--live`).
   Broker unreachable → simulator/fusion stream directly on the event bus, so
   Docker is not required.
2. **Twin** — `cd twin && npm run dev`. The map uses the SVG fallback when the
   Cesium token/network is unavailable; every panel labels its real data source.
3. **Live feed** (optional, if a network is actually present): `--live`. If the
   broker is unreachable the feed thread retries silently and `/api/live`
   reports `connected: false` — **non-fatal, the demo never depends on it**.

Offline checklist (`bash scripts/run_tests.sh`) must pass before you leave the
office. USB + cloud copies of the assets in §4.

---

## 3. Docker kill-and-recover drill

Docker runs an optional local MQTT broker + Postgres (not required for the demo,
but part of the production story).

```bash
# up
docker compose up -d

# the backend prefers the local broker/db when they are up; without Docker it
# falls back to in-process memory + direct-on-bus streaming (no config change)

# full reset (kill containers, wipe volumes, bring it back clean)
docker compose down -v
docker compose up -d

# recover from a wedged container
docker compose restart mqtt db
```

`POSTGRES_PASSWORD=vitish` and `allow_anonymous` mosquitto are **local-only** —
see the appendix in `docs/ROADMAP-NEXT.md` before any public deployment.

---

## 4. Demo assets list (what to copy to USB + cloud)

Everything the demo reads, with paths. Copy the whole list; it is the "one
laptop dies" insurance.

| Asset | Path | Size | Notes |
|---|---|---|---|
| Vibration models | `models/weights/{vae.pt,ocsvm.pkl,scaler.pkl,lstm_ae.pt,lstm_ae_meta.json,train_meta.json}` | ~230 KB | shipped trained ensemble (see §5 honesty) |
| Real crack segmenter | `models/weights/crack_seg.pt` | **92 MB** | YOLO26s-seg trained on CrackSeg9k |
| Z24 replay | `data/z24/inputs.npy` | 991 MB | real Z24 accelerometer replay |
| Crack dataset (CC0) | `data/cv/crackseg9k/` | ~5 GB | CC0; used by crack_seg.pt |
| Vibration dataset | `data/vib/hbta/` | ~2.5 GB | HBTA h5 |
| LTBP Markov priors | `data/ltbp/analysis/` | small | committed JSON — empirical fleet priors |
| Cesium token | `twin/.env` (`VITE_CESIUM_TOKEN=…`) | 1 line | **NEVER commit; copy separately** |
| Frontend build | `cd twin && npm run build` | — | `twin/dist/` static fallback |
| Backend + twin source | the repo | — | git tag `release-2026-08-13` |

**Dev-only datasets (never production / never on the pitch deck as licensed):**
dacl10k (CC BY-NC) and SDNET2018 (registration-gated) are research data only.

---

## 5. Runbook for the numbers (what is honest)

- **Demo arc** — `bash scripts/verify_gate.sh` (gate 15) + `scripts/verify_demo_arc.py`
  re-pin BHI 87.1 → AMBER 67.5 → RED 33.6 against the real replay.
- **Trained ensemble is ACTIVE on shipped state** — the 2026-08-15 retrain
  (non-degenerate scaler, real Z24) gives real separation: damaged-window
  trained deviation mean ~0.09-0.12 vs healthy ~0 (measured). The demo-scale
  synthetic stream stays inside the healthy envelope, so trained push stays ~0
  in the demo and the pinned arc is carried by the deterministic spectral floor
  in `backend/app/anomaly.py`. A degenerate-scaler guard remains: if a future
  scaler.pkl has a near-zero-variance feature, the ensemble is honestly declared
  INERT and push returns 0.0 rather than falsely scoring. `test_trained_path.py`
  (gate 10) pins the separation.
- **Live feed is a *demo of live ingestion*** — public-broker publishers are
  third-party and unvetted, tagged `source='public-mosquitto'`,
  `bridge='live-demo'`, never fused into the z24 BHI.
- **Never quote:** 4 cables, 18 days, EU mandate, 60 m, 690 citations, mAP 0.65,
  "BHI 87→12", "~15 s warm-up at default rate" (it is ~51 s; 15 s is the
  rate-3.4 figure). See `vault/05-Demo/QandA-Prep.md`.

---

## 6. Diagnostics

### "Stale 8000/8765 instance" (the classic demo-killer)

A previous backend is still holding the port, so your fresh `run_all` falls back
to 8001/8766 and the twin (or an old tab) talks to the STALE process. The banner
lies only if the port was contended at bind time — check what is actually serving:

```bash
# who holds 8000 / 8765?  (PowerShell — `wmic` is broken on Win 11)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000,8765 -State Listen | Select-Object LocalPort,OwningProcess | Format-Table"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'ProcessId=NNNN' | Select-Object ProcessId,Name,CommandLine | Format-List"

# kill the stale one (PID from above; note: the bash wrapper PID may differ from
# the real python PID — match the python command line, not the shell)
taskkill //F //PID NNNN

# then re-check the port is free
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue"
```

### Backend health

```bash
curl -s http://localhost:8000/health        # store: memory | postgres, broker reachable
curl -s http://localhost:8000/api/live      # live-feed status (--live only)
curl -s http://localhost:8000/api/manifest  # what each channel actually is
```

### Tests

```bash
bash scripts/verify_gate.sh      # 15-gate merge gate (incl. demo-arc re-pin)
bash scripts/run_tests.sh        # superset — every standalone backend test
cd twin && npm run lint && npm run test && npm run typecheck   # twin suite
cd twin && npm run build         # production build check
```

---

*Maintained as `docs/ROADMAP-NEXT.md` line 103. Last verified 2026-08-15 (all 15
gates pass on tag `arc-verified-2026-08-13`).*
