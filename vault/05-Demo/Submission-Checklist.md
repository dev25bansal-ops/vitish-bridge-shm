---
tags: [demo, submission, checklist, vitish-2026, shm]
created: 2026-08-15
---

# Submission Checklist — demo day (D-day)

> ROADMAP line 108. **REMAINING HUMAN ACTION:** every line is a physical step at
> the venue — walk this list. "Ready" below means the repo artifact exists; the
> packing/submitting is yours.

## The night before

- [ ] `bash scripts/verify_gate.sh` → **ALL 15 GATES PASS** (run on the
      `release-2026-08-13` tag) — READY
- [ ] `bash scripts/run_tests.sh` + `cd twin && npm run lint && npm test &&
      npm run typecheck` → all green — READY
- [ ] Copy to USB + cloud: RUNBOOK §4 asset list (weights incl. 92 MB
      crack_seg.pt, Z24 replay, datasets, Cesium token separately, this repo at
      the tag) — **the copy is yours**
- [ ] 2 backup takes recorded + in the same USB — yours
- [ ] Recharge both laptops + phone; charger + HDMI/VGA adapter + 3 m extension
      cord in the bag

## On the day

- [ ] **Submit 30 min early** (platforms stall under deadline load) — yours
- [ ] Walk-in bag check: laptops ×2, USB ×2 (one copy stays in the bag), phone,
      chargers, HDMI/VGA, tripod, printed RUNBOOK §6 + Storyboard
- [ ] Confirm venue GPU/environment (Risk #5): does the demo laptop need the
      network? It must NOT — offline order in RUNBOOK §2
- [ ] Rehearse the dataset-provenance answers (Q2/Q8/Q10/Q11 in [[QandA-Prep]])
      — a judge WILL ask "is that the real data?"
- [ ] Before walking on: cold-start order (RUNBOOK §1), pre-open the twin tab,
      silence notifications, screen-lock timer off
- [ ] 3-tier assets staged: **live** (running stack) primary · **video** (take 1)
      backup · **screenshots** (`demo-assets/` + conversation captures) last-resort
- [ ] Leave 5 min of air in the 6:00 script for a stalled demo — [[Rehearsal-Runbook]]

## The honesty card (tape to the laptop lid)

> BHI 87.1 → 67.5 → 33.6 · trained ensemble inert (floor carries arc) · live feed
> = demo of ingestion (never fused) · **NO LIVE badge** (ESP32 H8-gated stretch) ·
> never quote 4 cables / 18 days / EU mandate / 60 m / 690 citations / mAP 0.65.

Related: [[Rehearsal-Runbook]] · [[Pre-Hackathon-Checklist]] · [[QandA-Dry-Run]] · RUNBOOK
