---
tags: [demo, pitch, checklist, vitish-2026, shm]
created: 2026-08-15
---

# Idea Description + 10-Slide Deck (SIH submission kit)

> ROADMAP line 99. Submit-ready artefacts for the idea stage. The deck slides
> map 1:1 to the one-paragraph idea below. All numbers are the verified ones —
> nothing here overclaims (see [[Verified-Facts]]).

## One-paragraph idea (hits the 4 mandated components: problem · solution · innovation · feasibility)

> India inspects its ~1.7 lakh national-highway bridges on a periodic,
> largely-visual schedule — independent reporting tallies 170 collapses
> (2021–2025) against MoRTH's official 42, and the "structurally deficient"
> term was retired because periodic inspection misses slow damage. **VITISH**
> is a low-cost, instrumented structural-health-monitoring stack: a ~$980 pilot
> deploys MEMS accelerometers + a crack camera on one bridge, streams real
> telemetry over MQTT, fuses vibration + vision + load into a transparent
> Bridge-Health-Index (0–100, 3 sub-indices) with an uncertainty band, and
> renders a live digital twin. Its innovation is an honest data pipeline that
> says what every channel really is (real Z24 benchmark replay, public-broker
> live feed, or modelled synthetic — labelled on screen), a deterministic
> anomaly floor that cannot false-alarm the story arc, and Markov condition
> projections from real FHWA InfoBridge fleet priors. It is feasible now: the
> full stack is built and gate-tested (all 15 gates pass; demo arc 87.1 →
> AMBER 67.5 → RED 33.6 pinned), it runs offline on a single laptop, and it
> aligns 1:1 with MoRTH's IBMS digital-inventory drive (deadline 30 Sep 2026).

## 10-slide deck skeleton (20–25 s/slide)

1. **Problem** — the inspection gap: 170 media-tallied vs 42 official collapses;
   periodic visual inspection misses slow damage (Brazil Tocantins 2024, DNIT
   flagged cracks 4 years earlier).
2. **Solution** — VITISH: sensors → MQTT → transparent BHI (3 sub-indices) →
   live digital twin. One screen, every source labelled.
3. **Why the digital twin is the point** — a regulator sees *current state +
   confidence*, not a 0–100 black box. Uncertainty band → "high uncertainty
   means human review".
4. **How it detects damage (vibration)** — real Z24 benchmark replay through the
   real pipeline; mean+3σ healthy envelope; damage arc 87.1 → AMBER 67.5 → RED
   33.6, recovery returns to GREEN. (Honest: the trained VAE/OCSVM ensemble is
   ACTIVE on shipped state — it separates real damaged Z24 windows, but the
   demo-scale synthetic stream stays inside its healthy envelope, so the
   deterministic floor carries the arc.)
5. **How it detects damage (vision + load)** — real YOLO26s-seg crack segmenter
   (trained on CrackSeg9k) → regulator condition card; load sub-index fuses
   utilization. The production BHI never leans on vibration alone.
6. **The honest data pipeline** — the manifest: real Z24 replay vs public-broker
   live feed vs modelled synthetic, each labelled. Live ingestion demo
   (public MQTT, bridge `live-demo`) never fused into the hero BHI.
7. **Markov deterioration + temperature normalization** — condition projections
   from real FHWA InfoBridge fleet priors (44 LTBP pilot bridges); modal
   frequencies normalized against the seasonal drift Z24 itself shows.
8. **Cost** — pilot ~$980; scaled ~$260/bridge/yr; SaaS $25–30/bridge/month
   (deliberate MPU6050-class sensor downgrade for scale). Fits a state
   department's existing inspection budget line.
9. **Roadmap** — IBMS integration path (deadline 30 Sep 2026), pilot with a PWD
   bridge + a railway overbridge, BHI calibration against IRICEN CRN 0–6,
   real hardware edge node (H8-gated stretch).
10. **Ask / close** — partner with us on one pilot bridge; we ship the
    instrumented kit + the live twin in one field trip.

## Deck rules

- Every number must appear on the Q&A sheet ([[QandA-Prep]]/[[QandA-Dry-Run]])
  or be removed.
- Slide 4's honesty note is a feature, not a caveat — judges reward it
  ([[Key-Decisions]] #9/#11).
- Build from `pitch/metrics/metrics-sheet.md` (real measured numbers) and the
  live screenshots captured for [[Storyboard]].
