---
tags: [post-hackathon, roadmap, startup, vitish-2026, shm]
created: 2026-08-15
---

# Post-Hackathon Execution Brief (ROADMAP §4, lines 115-122)

> ROADMAP-NEXT Section 4 is titled **POST-HACKATHON** — every item needs a real
> partner, pilot data, incorporation, or post-event decisions. This brief turns
> each line into: **current state → first step → dependencies → acceptance
> criteria**. Nothing here is claimable as done; each item stays `[ ]` in the
> ROADMAP until its acceptance criteria are met. Hardware (line 114) is deferred
> per instruction — not covered here.

---

## 115 · RUL projection + realistic traffic/WIM load model

- **Current state** (repo): `AGE_FACTOR`/`TRAFFIC_FACTOR` are documented 1.0
  placeholders in [contract.py](../../backend/app/contract.py); load sub-index is
  scripted (`simulator.py`); Markov deterioration runs on real LTBP priors
  (`deterioration.py` + `data/ltbp/analysis/ltbp_summary.json`).
- **First step**: add remaining-life projection on the verified BHI trend — a
  band in the twin's HealthPanel. Use the LTBP cross-sectional deterioration
  curve (age vs condition) as the prior, the live BHI trend as the likelihood,
  and report "years to NBI ≤ 4" with an uncertainty band. Reuse the Markov
  machinery already built for line 34.
- **Dependencies**: a real load model needs bridge-specific traffic/WIM counts —
  either a partner's axle-load survey or published Indian WIM data. Until then
  keep `TRAFFIC_FACTOR=1.0` and say so on screen.
- **Acceptance**: RUL band renders in HealthPanel; number is reproducible from
  repo inputs; never-quote list in [[QandA-Dry-Run]] updated if a new figure
  enters the pitch.

## 116 · Realism items #11/#13/#14

- **Current state**: event-triggered capture/replay, component asset registry,
  crack-severity→image-to-3D photo registration — none built (these were the
  deferred realism extras in the D2 plan).
- **First step**: #11 event-triggered capture is the cheapest — reuse the
  existing alert path (`Store.insert_alert`) to snapshot the last N sensor rows
  on rupture onset and allow replay; the demo driver already marks onset. #13
  needs a backend model + frontend raycast card; #14 needs a camera registration
  pass (single-image, seeded on the Z24/S101 crack the demo already uses).
- **Dependencies**: none blocking; these are pure build. Time-box them.
- **Acceptance**: each ships behind its existing demo hook without moving the
  pinned arc.

## 117 · Complete the trained ML story

- **Current state** (honest): shipped `scaler.pkl` is degenerate (near-zero
  variance feature); the trained ensemble is **declared INERT** — the
  deterministic spectral floor owns the arc (the gate 15 banner says exactly
  this; see [Key-Decisions] #9/#11 and RUNBOOK §5). The trained-path gate (10)
  proves separation in principle on non-degenerate training.
- **First step**: real retrain with a non-degenerate scaler (drop the constant
  feature), then re-run the trained-path gate and re-pin the arc. This is the
  highest-integrity fix available and is **purely in-repo** — no partner needed.
- **Also in scope**: environmental de-confounding study (temperature-only → flat
  anomaly; already demonstrated on Z24, write it up), per-structure-type
  retraining, strain + acoustic channels.
- **Acceptance**: the inert banner can be honestly removed because the trained
  path contributes real separation on shipped state — measured, not assumed.

## 118 · CV scale-up

- **Current state**: real `crack_seg.pt` (YOLO26s-seg on CrackSeg9k, 92 MB) is
  the demo segmenter; `crack_unet.pt` never landed (train_unet.py exists);
  dacl10k 19-class fine-tune is a talking point only; MiniRocket+Ridge is
  reference-only (`minirocket_fallback.py`).
- **Decisions to make**: (a) retire `train_unet.py` or finish it; (b) dacl10k
  fine-tune stays a talking point (CC BY-NC — dev-only, never production);
  (c) SAM2 refinement pass — nice-to-have; (d) **MiniRocket+Ridge fate**: it was
  the honest alternative to the inert VAE/OCSVM — if line 117 lands, MiniRocket
  can be retired; if 117 stalls, it is the fallback for a trained vibration path.
- **Acceptance**: a written decision on each of the four, with the CV section of
  [Company-Project] §15 ledger row updated to match reality.

## 119 · BHI calibration study vs IBMS CRN 0-6

- **Current state**: the BHI is a transparent fused index with bands calibrated
  to the demo arc (87.1/67.5/33.6); NBI 0-9 mapping lives in
  `deterioration.py:condition_from_bhi`; IBMS (MoRTH digital inventory) deadline
  **30 Sep 2026** is the procurement hook.
- **First step**: write the calibration study protocol — for N pilot bridges
  with an IBMS CRN rating, regress CRN 0-6 onto the BHI sub-indices and pick
  bands/weights by agreement, not by arc aesthetics. This is a **named pilot
  deliverable**, so it needs a partner bridge first (see 120).
- **Dependencies**: pilot data. The study cannot start without it.
- **Acceptance**: a published mapping CRN ↔ BHI with a documented sample size,
  and the arc re-pinned only if the study says the demo band is wrong.

## 120 · Pilot deployment + startup track

- **Current state**: [Company-Project] is written; pricing ($980 pilot /
  ~$260/bridge/yr / $25-30/bridge/mo) is in the deck; the ask is one pilot
  bridge. No LOIs, no incorporation, no named CEO/BD.
- **Remaining human actions (blocking)**:
  1. Name the CEO/BD owning the pilot funnel.
  2. Partner PWD bridge + railway overbridge + one export → 2-3 LOIs.
  3. Incorporate + legal/IP review (algorithm + honest-data-pipeline method).
  4. Bottom-up India TAM (~1.7 lakh NH bridges) — write from real counts, not a
     slide number.
  5. Data-licensing plan: production data must be **commissioned**, not
     dacl10k/SDNET2018 (both dev-only — see [Data-Access-Checklist]).
  6. Competitor pricing depth + federated-learning moat case.
  7. IBMS integration path (deadline 30 Sep 2026).
  8. Refresh the $500k pre-seed ask with the pilot evidence.
- **Acceptance**: every one of the 8 has a dated owner and an artifact; nothing
  claimed in the pitch outruns what the repo + pilots can prove.

## 121 · Production data plane + CI

- **Current state**: anonymous localhost broker + public test.mosquitto.org
  dependency; `db_dsn` is env-only (opt-in Postgres); GitHub Actions CI runs the
  unified backend gate + twin typecheck/tests (already wired); numpy pinned
  ≥2.0; Cesium bundle ~1600 KB un-split.
- **First step** (in-repo, no partner): add auth/TLS to the broker config + a
  healthcheck; split the Cesium bundle (`dynamic import` on the geo layer);
  harden the CI matrix to the exact 15-gate script. CORS lock-down is queued
  here too.
- **Dependencies**: a real broker credential story for the pilot; otherwise all
  first-step items are pure build.
- **Acceptance**: `run_all` runs against a TLS+auth broker with zero anonymous
  fallback in production mode; CI green on a fresh checkout; bundle split proven
  by a Lighthouse-style size check.

## 122 · Publish + open-source the reusable pieces

- **Current state**: Z24 mirroring tooling, CrackSeg9k/SDNET conversion
  pipelines, `scripts/ltbp_analyze.py` Markov workflow — all exist in-repo and
  are the publishable nucleus. The honest-findings methodology (deterministic
  floor + bounded trained push, per-scenario evaluation) is the write-up.
- **First step**: draft the methodology paper/blog as the flagship; repackage
  the three tools as documented standalone scripts with READMEs + license
  headers. Keep dacl10k/SDNET **out** of any public artifact (licensing).
- **Dependencies**: legal sign-off on what may be published (line 120 legal/IP);
  none technical.
- **Acceptance**: a public repo or gist per tool + one methodology write-up,
  each with a license and a clear provenance section.

---

**Cross-links:** [Company-Project] · [Key-Decisions] · [Data-Access-Checklist] ·
[QandA-Dry-Run] · `docs/ROADMAP-NEXT.md` §4
