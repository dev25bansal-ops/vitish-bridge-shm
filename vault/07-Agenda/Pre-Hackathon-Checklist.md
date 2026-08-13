---
tags: [agenda, checklist, vitish-2026, shm]
created: 2026-08-13
---

# Pre-Hackathon Checklist (Day −14 → −1)

Do everything here BEFORE H0. This is what makes the 36 h survivable.

## Compliance & logistics (Day −14)

- [ ] Confirm VITISH roster = **6 members incl. ≥1 female**; unique team name **without the institute name**
- [ ] **Email/call organizers:** exact judging scorecard, demo format (live vs PPT), time limit, Q&A length, submission format, any idea-presentation template
- [ ] If no scorecard, assume SIH categories: problem understanding, innovation, technical execution/feasibility, impact, usability, presentation
- [ ] One-paragraph idea description hitting all 4 mandated components + 10-slide idea PPT

## Data & compute (Day −14 → −7)

- [ ] Download Z24 processed mirror (~992 MB) — office WiFi ([[Datasets]])
- [ ] **Register with KU Leuven** for official Z24 .mat (keep the confirmation email — the [[QandA-Prep]] Q4 license story)
- [ ] Download dacl10k v3 (~1.1 GB) + toolkit
- [ ] Download SDNET2018 (correct slug) + Ultralytics crack-seg
- [ ] Download Vänersborg (optional sanity check)
- [ ] Fetch US NBI coordinates for 50 real bridges
- [ ] Inventory GPU: team laptop(s) with CUDA, or a Colab/Kaggle notebook pre-staged with pinned torch+CUDA
- [ ] Pre-stage a working venv/Docker image with all pinned deps; verify `pip install` offline from cache

## Pre-compute (Day −7 → −3)

- [ ] dacl10k masks → YOLO-seg conversion (crack-only subset)
- [ ] Pre-train baseline binary crack segmenter (~2–4h GPU)
- [ ] Z24 hourly modal-frequency + temperature features → cached .npy
- [ ] Pre-train VAE+OCSVM + LSTM-AE; **verify anomaly rises on damage, flat on temperature-only**
- [ ] Build R3F twin shell with pinned versions + mock-data mode ([[Digital-Twin]])
- [ ] ESP32 firmware: WiFi + MQTT publish + rolling RMS flag — bench-tested
- [ ] Docker Compose (Postgres + EMQX/Mosquitto + app) — one command up
- [ ] Freeze message contract, BHI formula/weights, 6-min storyboard script
- [ ] Build demo-driver replay tool
- [ ] **Copy everything to USB + cloud. Verify it all runs with network OFF.**

## Pitch & Q&A (Day −3 → −1)

- [ ] Write 6-min pitch script draft + 15-second Morbi cold-open hook ([[Storyboard]])
- [ ] Lock the death-toll number against a primary source (official ~135 / Wikipedia 141)
- [ ] Build the Q&A bank with 2 owners; rehearse hostile questions ([[QandA-Prep]])
- [ ] Practice the demo on venue-class hardware; record 2 backup takes

Related: [[36h-Build-Plan]] · [[Datasets]] · [[Tech-Stack]] · [[Team]]
