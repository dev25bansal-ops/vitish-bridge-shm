---
tags: [agenda, roadmap, vitish-2026, shm, build]
created: 2026-08-13
updated: 2026-08-13
status: active
---

# 7-Day Build Roadmap — Hackathon is 7 days out, BUILD week

> **Frame:** the event starts ~2026-08-20. One week to build. The vibration/backbone is **done & verified** — this week is for the **one headline gap** (real CV crack detection), one **hardware stretch** (ESP32 real sensor), and demo **polish assets**. The verified demo arc is a **guardrail** — never break it.
> Anchors: [[Build-Log]] · [[Storyboard]] · [[QandA-Prep]] · [[Metrics]] · [[Pre-Hackathon-Checklist]] · [[36h-Build-Plan]]

## Honest gap analysis (what this week is really for)

| Piece | Status today | Value if built this week |
|---|---|---|
| Vibration (LSTM-AE/VAE/OCSVM) | **REAL** — weights + inference, arc verified | done |
| CV crack detection | **scripted** — `demo_driver.py` fires `cmd:cv 0.30/0.55`; no `crack_seg.pt`, no dataset | **highest** — makes the "Computer Vision" half of PS#99 true |
| IoT edge (ESP32 + IMU) | **absent** — docs only, no firmware | high, but needs hardware in hand |
| RUL / predictive maintenance | not built | medium polish |
| Per-scenario metrics | not generated | medium — Q&A depth |

**Guardrail (all week):** the verified arc GREEN 87 → AMBER 67.5 → RED 33.6 + no-flicker must hold after every change. Run `scripts/smoke_arc` (or the demo driver smoke) before calling any day done.

---

## Day 1 — Freeze baseline + CV data pipeline
- **Freeze & tag the verified build:** `git tag arc-verified-2026-08-13`. Any future change is measured against this.
- **Bring up CV data:** `python models/cv/prep_sdnet.py --dataset ultralytics` → downloads crack-seg (~92 MB) → builds `data/cv/yolo/` + auto `data.yaml`.
- **Sanity-train 3 epochs** — prove the loop runs, watch loss move, confirm `best.pt` lands.
- **Gate:** `crack-seg` present, one short training run completes end-to-end.

## Day 2 — Train real CV weights
- Train `yolov8s-seg` (or yolo11s/yolo26s via `--model auto`), ~30–50 epochs @ imgsz 512 on the GPU/CPU budget available.
- **Canonical output:** `models/weights/crack_seg.pt` (train_yolo copies it there).
- Produce **mAP@0.5 / F1 / precision / recall** on the held-out split → this becomes a [[Metrics]] asset.
- Verify `models/cv/inference.py` runs in **real mode** (`mode: yolo`) on test frames, not the heuristic.
- **Gate:** `crack_seg.pt` exists; a test frame yields real segment(s); metric numbers recorded honestly.

## Day 3 — Wire REAL cv into the live demo
- Curate **3–6 demo crack frames** (from the val split) into `data/cv/demo-frames/`.
- Add a small **`cv_feed`** service/bridge: at the storyboard's t=45 (→ cv 0.30) and t=85 (→ cv 0.55) moments, run the real image through `inference.py`, map detection area/confidence → cv evidence value, and emit it on the **existing** `control/cmd cv` path ([[contract.py]] already consumes it — no contract change).
- Keep the scripted value **only as fallback** if inference errors. Demo never hangs.
- **Re-verify the full arc** with real CV feeding `cv` — numbers must match [[Storyboard]] (within honest tolerance) and no flicker.
- **Gate:** live demo shows "CV: real detection" evidence; arc smoke green.

## Day 4 — ESP32 real sensor (parallel, hard-gated)
- **Only if a board is in hand** (ESP32 + MPU6050/ADXL345 ≈ $10–15). Build `firmware/`: read accel @ ~100 Hz, publish `sensors/z24/.../accel` over MQTT (same topic as simulator so the backend is agnostic).
- Lab: one IMU channel replaces one simulated channel at demo time → "real hardware in the loop."
- **Hard gate:** if no parts by end of Day 4 → **cut**, document as future work in [[Key-Decisions]]. Do NOT let hardware threaten the demo.
- **Gate:** real packets visible on the MQTT topic, backend consumes them.

## Day 5 — RUL + metrics assets (polish)
- **RUL / predictive maintenance:** remaining-life projection on the BHI trend (linear/AR on the verified trend), shown as a band in [[HealthPanel]] — small, self-contained.
- **Per-scenario confusion matrix** (settlement/spalling/hinge/anchor/tendon) from the Z24 mirror → [[Metrics]] asset ([[QandA-Prep]] Q7 depth).
- Package demo-frames + metric sheet into the pitch folder.
- **Gate:** RUL renders with real trend; matrix reproducible from one command.

## Day 6 — Full dress rehearsal (real CV + real sensor if landed)
- Cold start → full arc with **real CV** → map toggle → sensor popup → collapse → RUL. **Timed, recorded** (backup takes).
- Simulate failure (kill a container mid-demo) → recovery answer.
- **RUNBOOK.md** at repo root; `git tag release-2026-08-13`; pins + weights confirmed (`lstm_ae.pt, vae.pt, ocsvm.pkl, scaler.pkl, crack_seg.pt`).
- **Gate:** one clean 5-min run; `git status` clean.

## Day 7 — FREEZE
- **Demo freeze** — bugfixes only; every fix re-runs the arc smoke.
- Run [[Pre-Hackathon-Checklist]] top-to-bottom: roster (6 incl. ≥1 female), organizer scorecard email, KU Leuven registration, Z24 one-command mirror check.
- Pack: laptop, charger, HDMI, live-cam phone, backup drive, printed RUNBOOK.
- **Gate:** every box ticked; no uncommitted code.

---

## What we are NOT doing this week
- **No new vibration models / new scenarios** — vibration is done; touching it risks the arc.
- **No expanding the fleet / new UI panels** unless Day 5's RUL lands clean.
- **No unverifiable claims** in deck or answers ([[QandA-Prep]] rule).
