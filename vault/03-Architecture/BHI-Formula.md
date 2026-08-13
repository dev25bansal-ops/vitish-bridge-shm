---
tags: [architecture, bhi, ml, vitish-2026, shm]
created: 2026-08-13
---

# Bridge Health Index — transparent, not black-box

The 0–100 BHI is a real **Caltrans/AASHTO element-condition-state** construct ("100 = as-built, 0 = no remaining value"). Present it as condition-state aggregation, not an opaque formula.

## The formula

```
BHI = 100 × (1 − w_cv·cv − w_vib·vib − w_load·load) × age_factor × traffic_factor
```

## The 3 sub-indices

| Sub-index | Meaning | Source | Weight |
|---|---|---|---|
| `cv` | visual crack severity (0–1) | YOLO26s-seg ([[CV-Model]]) | 0.40 |
| `vib` | vibration novelty (0–1) | VAE+OCSVM anomaly score ([[Vibration-Model]]) | 0.35 |
| `load` | utilization / overload (0–1) | IoT stream | 0.25 |

Weights reflect **evidence reliability** — to be **re-calibrated on pilot data**, NOT "swept to maximize F1" (incoherent: Z24 has no images). See [[QandA-Prep]] Q8.

## Bands

| Band | Range | Action |
|---|---|---|
| 🟢 GREEN | ≥ 70 | normal |
| 🟡 AMBER | 50–70 | monitor / inspect |
| 🔴 RED | < 50 | flag for human review |

## Uncertainty band

- MC-dropout / ensemble spread → `u` field in the BHI message ([[Message-Contract]]).
- **High uncertainty → flag for human review** — this answers the #1 trust question.

## Honest Q&A framing

- "BHI = 78" means near-as-built on a 0–100 scale, aggregated from condition-state sub-indices ([[QandA-Prep]] Q11).
- Each sub-index maps to an auditable measurable (crack area, anomaly score, utilization).
- Calibration study against **IBMS CRN 0–6** (IRICEN) is a pilot deliverable ([[India-Policy]]).

Related: [[Message-Contract]] · [[Metrics]] · [[Vibration-Model]] · [[CV-Model]]
