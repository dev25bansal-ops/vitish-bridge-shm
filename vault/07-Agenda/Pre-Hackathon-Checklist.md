---
tags: [agenda, checklist, vitish-2026, shm]
created: 2026-08-13
---

# Pre-Hackathon Checklist (Day −14 → −1)

Do everything here BEFORE H0. This is what makes the 36 h survivable.

> Status banner 2026-08-15: **the entire build side of this checklist is done
> and gate-verified** (all 15 gates pass, demo arc pinned). What remains is the
> human logistics: roster, organizer email, actual KU Leuven registration
> submission, USB copy, venue rehearsal, and naming the 2 Q&A owners. Each
> remaining item has a repo artifact you can grab and act on in minutes.

## Compliance & logistics (Day −14)

- [ ] Confirm VITISH roster = **6 members incl. ≥1 female**; unique team name **without the institute name** *(human — decide who's on the team)*
- [ ] **Email/call organizers:** exact judging scorecard, demo format (live vs PPT), time limit, Q&A length, submission format, any idea-presentation template *(human — draft ready in [[Idea-and-Deck]])*
- [ ] If no scorecard, assume SIH categories: problem understanding, innovation, technical execution/feasibility, impact, usability, presentation
- [x] **One-paragraph idea description** hitting all 4 mandated components + **10-slide idea PPT** → **[[Idea-and-Deck]]** (2026-08-15, all verified numbers)

## Data & compute (Day −14 → −7)

- [x] Download Z24 processed mirror (~991 MB) — `data/z24/inputs.npy` ✅
- [ ] **Register with KU Leuven** for official Z24 .mat → **ready-to-send cover note + steps in [[Data-Access-Checklist]] #1** *(human: submit the form, keep the email)*
- [x] Download dacl10k v3 + toolkit → `data/cv/dacl10k` (8,922 files verified) ✅
- [x] Download SDNET2018 (correct slug) + Ultralytics crack-seg → `data/cv/sdnet2018` ✅ (dev-only, registration-gated)
- [ ] Vänersborg (optional sanity check) — skip unless needed
- [x] Fetch US NBI coordinates for 50 real bridges → `backend/app/regulator_bridges.py` (50 real fleet + hero at Nottwil) ✅
- [x] Inventory GPU / pre-staged Colab: training **already done** (crack_seg.pt, vae, ocsvm, lstm_ae) — no GPU needed at the venue ✅
- [x] Pre-stage a working venv/Docker with all pinned deps; offline pip cache — `requirements.txt` + venv verified; offline run works (RUNBOOK §2) ✅

## Pre-compute (Day −7 → −3)

- [x] dacl10k masks → YOLO-seg conversion (crack-only subset) → `models/cv/prep_crackseg9k.py` ✅
- [x] Pre-train baseline binary crack segmenter → `models/weights/crack_seg.pt` (YOLO26s-seg, CrackSeg9k) ✅
- [x] Z24 hourly modal-frequency + temperature features → cached → stiffness overlay + temperature normalization (gates 2/6) ✅
- [x] Pre-train VAE+OCSVM + LSTM-AE; **verify anomaly rises on damage, flat on temperature-only** → trained-path gate 10 ✅ (honest: shipped scaler is inert by design — see RUNBOOK §5)
- [x] Build R3F twin shell with pinned versions + mock-data mode → `twin/` (58 vitest tests) ✅
- [ ] ESP32 firmware: WiFi + MQTT publish + rolling RMS flag — bench-tested → **H8-gated stretch, deferred** (firmware/ + tools/ in repo; no board flashed) — see [[Key-Decisions]] #11
- [x] Docker Compose (Postgres + Mosquitto + app) — `docker-compose.yml` (optional; broker falls back) ✅
- [x] Freeze message contract, BHI formula/weights, 6-min storyboard script → `backend/app/contract.py` + [[Storyboard]] ✅
- [x] Build demo-driver replay tool → `backend/app/demo_driver.py` (gate 14 beat-timing) ✅
- [ ] **Copy everything to USB + cloud. Verify it all runs with network OFF.** → asset list in RUNBOOK §4; verify script: `bash scripts/run_tests.sh` offline *(the USB copy itself is human)*

## Pitch & Q&A (Day −3 → −1)

- [x] Write 6-min pitch script draft + 15-second Morbi cold-open hook → [[Storyboard]] + [[Idea-and-Deck]] slide 1–10 ✅
- [x] Lock the death-toll number against a primary source → **~135 (55 children) / Wikipedia "at least 141"**, in [[Verified-Facts]] ✅
- [ ] Build the Q&A bank with **2 owners**; rehearse hostile questions → bank done ([[QandA-Prep]] + [[QandA-Dry-Run]]), **owners = human naming**; run the dry-run drill
- [ ] Practice the demo on venue-class hardware; record 2 backup takes → rehearsal runbook in RUNBOOK §6 + [[Storyboard]] *(venue practice is human)*

Related: [[36h-Build-Plan]] · [[Datasets]] · [[Tech-Stack]] · [[Team]] · [[Key-Decisions]]
