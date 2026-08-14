---
tags: [build, log, vitish-2026, shm]
created: 2026-08-13
---

# Build Log

Running log of the 36-hour build. Newest entries at TOP. One row per significant work block; keep it terse — the git history is the detailed record.

## Template

| Date/time | Task | Status | Next |
|---|---|---|---|
| 2026-08-14 | **D1-1 (2-day plan) — demo arc PINNED as a regression gate**: `backend/tests/test_demo_arc.py` forces the deterministic spectral-heuristic floor (`trained_push → 0`) and asserts the full story deterministically on any clone, zero data: baseline GREEN in [75,90] → cv beat drops BHI but stays GREEN → 61-step seeded cross-fade passes through AMBER and never returns to GREEN → load+cv escalation → RED in [20,45] → RED stays stable, no flicker. **11/11 PASS**. `scripts/verify_gate.sh` = smoke (83/83) + arc gate, the pre-push merge gate. Values re-pinned against real data by `scripts/verify_demo_arc.py` (data-dependent, next) | ✅ done | D1-2 bridge-identity decision (30 m box girder vs cable-stayed) + D1-3 condition card |
| 2026-08-13 | **LSTM-AE trained + arc re-verified (no flicker)**: `lstm_ae.pt` (30 epochs, P95 recon threshold 3.0e-7, 4050 real-Z24 healthy windows) now loads in the ensemble → **"VAE/OCSVM · envelope-floor+push + LSTM-AE"**. Measured the trained push on real Z24: healthy ≈ **0.003** (envelope absorbs jitter — no false alarm), real damage ≈ **0.14**, damage + rupture overlay ≈ **0.17** — the trained models genuinely contribute without breaking the arc. Also root-caused + fixed a **GREEN→AMBER→GREEN→RED flicker** at 81–85 s: the demo's tendon-snap impact pulse inflated the floor's baseline RMS ~6000× in one window (8.6e-6 → 5.4e-2), so the real damage signature read as "normal" until tonality overcame it. Fix: gate the healthy-envelope refit on `r_ratio <= 1.5` (`anomaly.py`). **Definitive real run (LSTM loaded, Postgres-verified): GREEN 87 → 76–78 (crack 45 s, cv 0.30) → AMBER 67.5 at 75 s onset → RED 49.8 at ~90 s → RED 33.6 at 110 s (bhi-drop beat) → holds RED; NO flicker; alerts at 45/75/110/140 s; backend smoke 83/83** | ✅ done | 6-min demo rehearsal on the locked timeline ([[Storyboard]]) |
| 2026-08-13 | **Integration verified end-to-end**: Docker infra (MQTT 1883/9001 + Postgres healthy) · backend `run_all.py --demo` boots (real Z24 replay, WS :8765, API :8000) · MQTT pipeline live (22 msgs/6s: accel/bhi/alert/status) · twin LIVE over WS, auto-reconnect REPLAY→LIVE, full story (crack→vib→BHI RED 49.9→critical alert→copilot) · backend smoke 83/83 · models smoke 19/19 · twin `npm run build` ✓ | ✅ done | Rehearse 6-min script on demo timeline |
| 2026-08-13 | Twin ws.ts fix: `ws://127.0.0.1:8765` (avoid localhost→::1 race) + 5s retry loop so REPLAY→LIVE handoff is automatic | ✅ done | — |
| 2026-08-13 | Digital twin (R3F) built + live-verified: parametric Morbi bridge, sensors, SVG fleet map, BHI gauge, alerts, copilot, story controls, collapse arc | ✅ done | — |
| 2026-08-13 | ML models built (vibration VAE/OCSVM + LSTM-AE + MiniRocket + heuristic, CV YOLO + OpenCV fallback, BHI fusion) — all with zero-weights demo fallbacks | ✅ done | Real Z24 training (36h stretch) |
| 2026-08-13 | Backend pipeline built: simulator (Z24 replay + synthetic fallback + damage injector), MQTT, Postgres+memory store, WS bridge, FastAPI, demo driver | ✅ done | — |
| 2026-08-13 | Vault knowledge base created (26 notes) | ✅ done | Start [[Pre-Hackathon-Checklist]] items |
| — | — | — | — |

## 36-h build phase trackers

- Phase 0 Freeze (H0–H2) — verify pre-built assets, freeze stack + hero flow
- Phase 1 Core models + pipeline (H2–H10) — CV fine-tune, VAE+OCSVM, simulator→MQTT→Postgres; **H8 ESP32 gate**
- Phase 2 Twin + integration (H10–H16)
- Phase 3 Integration + first rehearsal (H16–H24)
- Phase 4 FEATURE FREEZE (H24–H32) — metrics, hardening, backup videos; presenter stops coding ~H28
- Phase 5 Demo freeze + dry run (H32–H35.5) — submit 30 min early

Details: [[36h-Build-Plan]].

## Live status

- ✅ Research (12-agent workflow) complete
- ✅ Master build plan written
- ✅ Vault knowledge base curated
- ✅ Backend pipeline, ML models, digital twin built (4-agent build workflow)
- ✅ **End-to-end integration verified** — simulator→MQTT→subscriber→bus→WS/API→twin live; story runs 87 GREEN → RED → alert → copilot
- ✅ Smoke tests green (backend 83/83 · models 19/19); twin `npm run build` clean
- 🔜 **Next**: 6-minute demo rehearsal ([[Storyboard]] timeline), real Z24 training (stretch), [[Pre-Hackathon-Checklist]]

Related: [[Team]] · [[Data-Pipeline]] · [[CV-Model]] · [[Vibration-Model]] · [[Digital-Twin]]

---

Status: ✅ core build + integration verified — in demo-rehearsal phase
