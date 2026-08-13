---
tags: [agenda, roadmap, vitish-2026, shm, demo-ready]
created: 2026-08-13
updated: 2026-08-13
status: active
---

# 7-Day Roadmap — Build Complete → Demo-Ready

> **State at Day 1 (2026-08-13):** engineering is **DONE and verified**. No new features. These 7 days turn a working build into an **unmissable, unbreakable demo** + the pitch/Q&A/logistics that win points.
> Anchors: [[Build-Log]] · [[Storyboard]] · [[QandA-Prep]] · [[Metrics]] · [[Pre-Hackathon-Checklist]] · [[36h-Build-Plan]]

## Verified baseline (what we stand on)

| Asset | Proof |
|---|---|
| Demo arc | GREEN 87 → AMBER 67.5 (75s) → RED 49.8 (≈90s) → RED 33.6 (110s), **no flicker**; alerts 45/75/110/140s |
| Backend | smoke 83/83 |
| Models | 19/19 (VAE/OCSVM · envelope-floor+push + LSTM-AE, push healthy 0.003 / damage 0.14–0.17) |
| Twin | production build clean; light theme; toggle-map verified |
| Data | Z24 full mirror 946 MB; 1530 windows |
| Infra | Docker MQTT + PostgreSQL, DB user `vitish` |

**Rule for all 7 days:** *Never claim a number or feature stronger than what's in the repo* ([[QandA-Prep]]). Everything below respects that.

---

## Day 1 — Harden: make it indestructible
**Goal:** a demo that survives cold-start, no-network, and a dead laptop.

- **Write the RUNBOOK** at repo root (`RUNBOOK.md`): exact order — `docker compose up -d` → `python -m app.run_all` (or `demo_driver.py`) → `npm run dev` → open `http://localhost:PORT`. Step-by-step, screenshots. *This is the file a stranger uses to run us.*
- **Offline drill:** kill Wi-Fi, confirm map falls back to SVG ([[Digital-Twin]]), MQTT/PG run local-only.
- **Capture 2 backup takes** (OBS or phone, 1080p): full arc GREEN→RED, no narration (voice-over later). Store in `backup/demo-2026-08-13/`.
- **Trim:** grep out debug prints / stray logs that could leak during demo.
- **Gate:** cold start on a clean clone works in < 5 min with RUNBOOK only.

## Day 2 — Metrics to the front: show ML rigor
**Goal:** judges see *measured* evidence, not a single F1.

- **Generate + commit assets** (see [[Metrics]]): confusion matrix by Z24 scenario, threshold-vs-FPR curve, per-class precision/recall, latency table (streaming ~200 ms; detection ~10.5 s + inference). Script them under `scripts/eval_*.py` so they re-run on demand.
- **Pin 3 dashboard stills** from the live arc (GREEN / AMBER / RED) for the pitch deck + backup slides.
- **Gate:** every number on the asset sheet maps to a command in the repo (reproducible).

## Day 3 — Pitch: deck, one-pager, 5-min script
**Goal:** 60 seconds to make a judge lean in.

- **10-slide idea PPT** ([[Pre-Hackathon-Checklist]]): Problem → IoT+CVA+Twin → BHI auditability → Demo screens → Cost table ([[Metrics]] #9) → Roadmap → Team.
- **One-paragraph description** + **solution PPT** (same checklist).
- **Turn [[Storyboard]] into a timed 5-minute walk-through**: which clicks, when, what you say. Assign one owner.
- **Gate:** pitch run-through in < 60 s; demo script under 5:00.

## Day 4 — Q&A rehearsal + compliance (human items)
**Goal:** nothing to panic-email on the day.

- **Q&A rehearsal:** 2 owners run the full [[QandA-Prep]] (12 answers) cold; mark weak spots; one answer per weak spot.
- **Roster:** finalize 6 members incl. ≥ 1 female (compliance).
- **Email organizers** for the VITISH scoring rubric/scorecard — know *how we're judged*.
- **KU Leuven registration** (license story — Q4 in [[QandA-Prep]]).
- **Z24 verification:** one command re-downloads/mirrors if the 946 MB is ever lost.
- **ESP32 decision gate:** it's already cut from the build — **keep it cut**, listed as future work. Do not resurrect 48h before an event.
- **Gate:** 12/12 answers pass cold; roster + registrations done.

## Day 5 — Full dress rehearsal (recorded)
**Goal:** the live show, end to end, on the real laptop.

- Full stack cold start → demo arc → map toggle → sensor popup → collapse → panels. **Timed.**
- **Backup take 3** recorded here (the best one).
- Simulate a failure: kill a container mid-demo; confirm recovery story (this becomes a Q&A answer).
- **Gate:** one clean 5-min run, recorded, no dead air.

## Day 6 — Venue readiness + repo hygiene
**Goal:** arrive with nothing to fix on site.

- **Venue dry-run:** projector resolution (720p/1080p — resize HUD if needed), audio, HDMI, second laptop as live-cam for the audience.
- **Network plan:** tiles need internet; MQTT/PG local. Know which is which.
- **Repo hygiene:** commit all Day 1–5 assets, `git tag release-2026-08-13`, `package-lock`/`requirements.txt` pinned, weights confirmed (lstm_ae.pt, vae.pt, ocsvm.pkl, scaler.pkl).
- **Gate:** `git status` clean; tag present; venue checklist ticked.

## Day 7 — FREEZE + day-before checklist
**Goal:** no surprises; sleep.

- **Demo freeze:** no feature changes, only bugfixes if a *judged* risk surfaces. Every change re-runs the full arc smoke.
- **Run [[Pre-Hackathon-Checklist]] top to bottom** — tick every box.
- **Pack:** laptop, charger, HDMI adapter, phone/stand for live-cam, backup drive, printed RUNBOOK + scorecard email + roster.
- **36h briefing:** reread [[36h-Build-Plan]] as a team; assign Phase 0 roles so the first 2 hours of the event are instinct.

---

## What this does NOT include (deliberately)
- **No new features** after Day 1 (ESP32, extra sensors, more scenarios). The build is complete; additions now only add risk.
- **No unverifiable claims** in deck or answers ([[QandA-Prep]] rule).
