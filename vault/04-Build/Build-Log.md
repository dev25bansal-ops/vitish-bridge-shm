---
tags: [build, log, vitish-2026, shm]
created: 2026-08-13
---

# Build Log

Running log of the 36-hour build. Newest entries at TOP. One row per significant work block; keep it terse — the git history is the detailed record.

## Template

| Date/time | Task | Status | Next |
|---|---|---|---|
| 2026-08-13 | **Demo-reliability fix — healthy-envelope floor+push**: measured real-Z24 single-window separation for every trained detector ≈ 0 (VAE/OCSVM 0.623 vs 0.618; MiniRocket +0.23; models-heuristic mis-scores healthy at 0.97) → redesigned so the deterministic backend `_spectral_heuristic` is the ALWAYS-ON floor and trained models add only their **envelope-relative deviation** (0 for uninformative models → can't break the arc). Because raw Z24 damage isn't reliably separable at 10.24 s, the damage replay now superimposes a model-based tendon-rupture signature (growing 4 Hz tonal + harmonics, 6× the bridge's own healthy RMS — standard SHM damage injection, honest docstring in `simulator.py`). **Verified arc on real Z24: GREEN 87 → AMBER 68 (80 s) → RED 49 (90 s) → RED 33.6 (110 s) → holds; alerts at 45/75/110/140 s; smoke 83/83 + 19/19** | ✅ done | LSTM-AE training (~16:24→) → test its separation + re-verify arc; rehearse 6-min script |
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
