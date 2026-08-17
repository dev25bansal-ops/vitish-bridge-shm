---
tags: [demo, metrics, ml, vitish-2026, shm]
created: 2026-08-13
---

# Metrics — what to MEASURE and report

Never present a single headline number. Show the breakdown; honesty reads as confidence ([[QandA-Prep]]).

## CV

- **mAP@0.5 on your own 70/20/10 split** of the binary crack set — on screen.
- Do NOT state 0.65 as fact (best published dacl10k mIoU is 0.42; your own split differs).
- F1 / precision / recall on curated demo frames with visible cracks.

## Vibration

- **Full confusion matrix by Z24 scenario** (settlement, spalling, hinge, anchor-head, tendon rupture), not one F1.
- Window = 10.24 s @ 100 Hz; positive = reconstruction error > mean + 3σ of healthy-only envelope ([[Vibration-Model]]).
- F1 0.85+ / FPR 4% are **build-time measured targets**, not claims.
- Report the threshold-vs-FPR curve (for [[QandA-Prep]] Q7).

## Latency (state both deliberately — [[Verified-Facts]] #10)

| Path | Target |
|---|---|
| Streaming telemetry (10+30+50+100 ms) | **~200 ms** |
| Anomaly detection (full 10.24 s window + inference) | **~10.5 s + inference** |

## Cost table (corrected — [[Key-Decisions]] #9)

| Line | Value |
|---|---|
| Pilot BOM (10 nodes, one bridge) | **~$980** (~$810–1,080 range) |
| Scaled recurring (1,000+ bridges, MPU6050-class downgrade stated) | **~$260/bridge/yr** (≈$21.7/mo) |
| Recommended SaaS price | **$25–30/bridge/mo** (above amortized TCO) |

Never print: $560, $300, $5–15/mo, $10–50/mo.

## Demo beat numbers

- BHI 87 → **34** (RED, verified arc 87.1 → 77.7 → AMBER 54 → 33.6, [[Storyboard]]) on the scripted damage cascade.
- **N days** before final rupture — measured from actual threshold crossing (≈30 settlement, ≈15 spalling), labeled on screen.

Related: [[Storyboard]] · [[CV-Model]] · [[Vibration-Model]] · [[BHI-Formula]]

## Measured — 2026-08-16 (`scripts/metrics_sheet.py`)

- **Demo scenarios**: precision 1.0 · recall 1.0 · F1 1.0 (healthy mean 0.0737 vs rupture mean 0.4771, threshold mean+3σ = 0.1914).
- **Z24 benchmark**: precision 0.5263 · recall 0.0016 · F1 0.0032 — honest current state; the synthetic-tuned floor does not separate real Z24 scenarios, the trained VAE/OCSVM ensemble is ACTIVE on shipped state — mode `VAE/OCSVM (vae.pt, mode=features, latent=16) + LSTM-AE · envelope-floor+push`; real Z24 separation (damaged dev mean ~0.09-0.12 vs healthy ~0, measured) (Q&A Q3/Q7).
- **crack_seg val**: mAP@0.5 0.0826 (full PR curve; cross-check ultralytics val 0.074) · @0.25 precision 0.4256 · recall 0.057 · image-level recall 0.9747 (500/513).

---






