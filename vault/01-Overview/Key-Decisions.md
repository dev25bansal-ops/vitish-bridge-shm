---
tags: [overview, decisions, vitish-2026, shm]
created: 2026-08-13
---

# The 10 Key Decisions

The decisions that changed the research report (master plan §1). These are frozen; the build follows them literally.

| # | Decision | Why |
|---|---|---|
| 1 | **Simulator-first, live-second** — replay Z24 through the real pipeline; one ESP32 is a stretch goal | Venue WiFi/batteries/MQTT are the classic demo-killers; a deterministic replay is a 100% safety net |
| 2 | **Binary crack segmentation on SDNET2018** in the 36h; dacl10k is pre-hackathon only | dacl10k is 18-class, multi-label, imbalanced (mIoU 0.42); SDNET2018 (56k binary, balanced) trains in 2–4 h with clean overlays |
| 3 | **YOLO26s-seg** (Jan 2026), not YOLOv8 | YOLOv8 is 3 generations old; one-line swap in Ultralytics; "why not YOLO12/26?" neutralized |
| 4 | **VAE+OCSVM** primary vibration model (PR 0.996 / recall 0.999 on Z24); LSTM-AE edge baseline; MiniRocket fallback | Better published numbers, same pipeline, canned answer for "why this model?" |
| 5 | **Temperature-compensated** Z24 features | Z24's modes swing ~10% with season vs ~1–2% for damage; a raw AE flags weather as damage |
| 6 | **Transparent BHI** — 3 sub-indices + uncertainty band | "High uncertainty → human review" answers the #1 trust question; not an opaque 0–100 formula |
| 7 | **Pre-built twin shell**, pinned versions (R3F ^9.7 + React 19.2 + three 0.185) | React 19.2 broke R3F <9.5; three 0.185 ships zero .d.ts; version churn eats 2–4 h |
| 8 | **Reframed Morbi claim** — motivation, not validation | Morbi had no sensors (untestable) and is the *opposite* of Z24's induced damage; the reframe turns a kill-shot into differentiation |
| 9 | **Corrected cost math** — pilot ~$980, scaled ~$260/bridge/yr, SaaS $25–30/mo | The old $300 / $5–15 numbers were wrong arithmetic a business-savvy judge would do |
| 10 | **Corrected facts** — Morbi 135 (some tallies 141), suspension bridge, drop "4 cables" and "18 days" | Unverified claims get dismantled on stage; see [[Verified-Facts]] |

## The single biggest insight

Every failure mode above is mitigated by the same move: **pre-build everything that can be pre-built** (data, models, twin shell, Docker Compose, message contract, demo script) before H0 — the 36 h are integration, tuning, and rehearsal, not discovery. See [[Pre-Hackathon-Checklist]].

Related: [[Four-Components]] · [[System-Architecture]] · [[Verified-Facts]]
