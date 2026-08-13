---
tags: [agenda, build-plan, vitish-2026, shm]
created: 2026-08-13
---

# The 36-Hour Build Plan

Hour-by-hour, with **hard gates at H8, H24, H32**. Phase trackers also in [[Build-Log]].

## Phase 0 · H0–H2 — Freeze (parallel tracks start)

- H0: verify pre-built assets run in the venue environment; inventory GPU; smoke-test ESP32 on the local broker
- H0–H1: freeze stack, roles, the ONE hero demo flow, and the 90-second demo script — BEFORE meaningful code
- H1–H2: 3 parallel tracks start (embedded/backend · CV · vibration ML; twin track starts at H10)

## Phase 1 · H2–H10 — Core models + data pipeline

- H2–H6: CV — fine-tune binary crack segmenter on SDNET2018/crack-subset (2–4h GPU), evaluate on demo frames
- H6–H10: vibration — train VAE+OCSVM / LSTM-AE on temp-compensated Z24 features, calibrate threshold on damage month, wire BHI
- H2–H8: pipeline — simulator → Mosquitto → Postgres → live chart working
- **H8 HARD GATE:** real ESP32 node streaming? If not, cut it (simulator is authoritative)

## Phase 2 · H10–H16 — Twin & integration

- H10–H16: wire twin to data bus ([[Digital-Twin]] 8-h order), crack overlay + amplified deflection, dashboard

## Phase 3 · H16–H24 — Integration & first rehearsal

- H16–H20: full-stack integration in **replay mode**; end-to-end test of the hero flow
- H20–H24: first storyboard rehearsal; fix the 3 worst things; **team rest/meal break**

## Phase 4 · H24–H32 — FEATURE FREEZE (no new features)

- **H24 HARD GATE:** FEATURE FREEZE. Switch to: real metrics (mAP / confusion matrix / RMSE), hardening, backup video recording (2 takes), pitch drafting
- H28: presenter stops coding; rehearses timed 6-min pitch ≥3× (once to a stranger/mentor); Q&A bank owners finalize
- H28–H32: 3-tier demo assets (live → video → screenshots) on 2 laptops + 1 phone; live-sensor smoke test

## Phase 5 · H32–H35.5 — Freeze & dry run

- **H32 HARD GATE:** DEMO FREEZE — if anything is still broken, cut the live sensor path, run 100% on replay (all 4 mandated components remain demonstrable)
- H34: full 6-min dry run with timer + projector/audio/scaling
- H35: submit **30 minutes early**, not 30 seconds early
- H35.5: walk-in bag check (2 laptops, spare batteries, USB-C hub, ethernet adapter)

## Sleep & cadence

- 2-shift rotation, ≥4 awake at all times, 4–6h continuous sleep per member.
- Presenter gets 8h the night before demo day. **No all-nighters after H24.**
- Commit every 1–2h ([[Team]]).

Related: [[Pre-Hackathon-Checklist]] · [[Risk-Register]] · [[Storyboard]] · [[Build-Log]]
