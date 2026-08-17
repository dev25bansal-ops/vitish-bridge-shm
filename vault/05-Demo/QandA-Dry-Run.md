---
tags: [demo, qna, checklist, vitish-2026, shm]
created: 2026-08-15
---

# Q&A Bank Dry-Run — corrected-facts rehearsal

> ROADMAP line 106. Rehearse ONLY the corrected facts below. Format: 2 owners,
> alternate hostile rounds, a stopwatch, and a note-taker. One line per fact =
> one dry-run prompt. **Never quote anything not on this sheet.**

## The landmines (know the exact framing, then pick ONE number deliberately)

| Landmine | Correct framing (verified, [[Verified-Facts]]/[[Global-Failures]]) |
|---|---|
| **170-collapse vs MoRTH-42** | "Independent media reporting (Newslaundry) tallies **170 bridge collapses / 202 deaths / 441 injured in India 2021–2025**; MoRTH's official count is **42 collapses 2019–2024**. The gap is a reporting-vs-official discrepancy we flag openly rather than pick a side — and it's exactly why we push for continuous, instrumented monitoring instead of periodic inspection." |
| **US 42,000 structurally deficient** | The "structurally deficient" term was **retired in 2022** (FHWA uses "poor condition"). Never say "42,000 structurally deficient". |
| **Z24 60 m vs 58 m** | Z24 is **58 m**, first modes ~3.5–4.5 Hz. (The old 60 m was the audit-corrected error.) |
| **Morbi 4 cables / 18 days** | Never quote "4 corroded cables" or "18 days before failure". Say: **rusted cables, broken anchors, loose bolts, heavy new flooring** (forensic report); toll ~135 (55 children) / Wikipedia "at least 141". |
| **EU mandate** | No EU/UK/Netherlands smart-sensor mandate is verified — do not claim one. |
| **690 citations / mAP 0.65** | Both were corrected away. Z24 environmental paper has **>1,000 citations**; no mAP 0.65 claim exists in the repo. |

## The three numbers to state deliberately (memorized)

1. **Cost table** — pilot **~$980**; scaled **~$260/bridge/yr**; realistic SaaS
   **$25–30/bridge/month** (not $5–15). The $300 scale figure assumes the
   deliberate MPU6050-class sensor downgrade — state it if probed ([[Key-Decisions]] #9).
2. **Latency split** — **~200 ms** is streaming telemetry only (10+30+50+100 ms).
   Anomaly needs a full **10.24 s window** → **~10.5 s + inference**. State both
   deliberately; never one number for both.
3. **Demo arc** — BHI **87.1 → AMBER 67.5 → RED 33.6**, pinned by
   `scripts/verify_demo_arc.py` against the real Z24 replay. Recovery returns to
   GREEN. No flicker, no "87→12".

## Standing guardrails (repeat from [[QandA-Prep]])

- Never claim a number or feature stronger than what's in the repo.
- Trained ensemble is **ACTIVE on shipped state** (non-degenerate retrain): it
  separates real damaged Z24 windows, but the demo-scale synthetic stream sits
  inside its healthy envelope, so `trained_push` stays ~0 and the deterministic
  spectral floor carries the arc. Say exactly that.
- Live feed = **demo of live ingestion** (public broker, unvetted, `live-demo`,
  never fused into z24 BHI).
- **No LIVE badge** — ESP32 is the H8-gated stretch ([[Key-Decisions]] #11);
  firmware + backend monitor exist, no board flashed/bench-tested.
- dacl10k (CC BY-NC) + SDNET2018 (registration) are dev-only research data.

## Dry-run drill

- **Round 1 (2 min/each):** owners read the 12 canned answers in [[QandA-Prep]]
  aloud with a timer; any stumble → re-read.
- **Round 2 (hostile):** the room plays the *most aggressive* judge: "FPR 4%?",
  "registration?", "show a packet from the ESP32", "prove it prevented Morbi",
  "your cost math", "170 vs 42 — which is it?", "is this pre-recorded?".
- **Round 3 (data):** open `pitch/metrics/per-scenario-confusion-matrix.md` and
  explain recall **0.002** vs demo envelope **1.0** — you must not flinch.
- **Close:** both owners sign the dry-run sheet (who owns Q1–Q6 / Q7–Q12).

Related: [[QandA-Prep]] · [[Verified-Facts]] · [[Metrics]] · [[Storyboard]]
