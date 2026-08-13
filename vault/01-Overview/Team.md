---
tags: [overview, team, vitish-2026, shm]
created: 2026-08-13
---

# Team — 6 roles

| # | Role | Mandate | Stop coding |
|---|---|---|---|
| 1 | **Embedded / data pipeline** | Z24 replay simulator, MQTT, ESP32 firmware bring-up (H4–H8), broker, Postgres | H24 |
| 2 | **CV / crack model** | YOLO26s-seg fine-tune, SDNET2018 pipeline, mask conversion, SAM2 (optional), webcam hookup | H24 |
| 3 | **Vibration / anomaly ML** | VAE+OCSVM + LSTM-AE on temp-compensated features, threshold calibration, uncertainty, MiniRocket fallback | H24 |
| 4 | **Digital twin + dashboard** | R3F wiring, MapLibre map, BHI gauge, copilot pane | H24 |
| 5 | **Backend / integration OWNER** | Owns the single hero demo flow end-to-end, Docker Compose, message contract, demo-driver replay | H24 |
| 6 | **Presenter** | Owns pitch script + deck from hour 0 | **~H28** — then rehearses only |

## Rules

- **30-second explanation:** all 6 must explain their own component's data, training, and failure modes in 30 s (feeds [[QandA-Prep]]).
- **Commit cadence:** commit every 1–2 h — the git history must show honest continuous build work.
- **Tracking:** GitHub Issues; one issue per beat of [[36h-Build-Plan]].
- **Sleep shifts:** 2-shift rotation, ≥4 awake at all times, 4–6 h continuous sleep per member, **no all-nighters after H24**, presenter gets 8 h the night before demo day.
- **Hard gates:** H8 cut the live ESP32 if not streaming; H24 feature freeze; H32 demo freeze ([[36h-Build-Plan]]).
- Standing rule: never claim a number stronger than what's in the repo ([[QandA-Prep]]).

Related: [[Mission]] · [[Key-Decisions]] · [[Build-Log]]
