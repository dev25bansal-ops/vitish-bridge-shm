---
tags: [research, dataset, z24, vitish-2026, shm]
created: 2026-08-13
---

# Z24 Bridge Benchmark (KU Leuven)

The **fuel of the build** — a real, citable progressive-damage dataset replayed through the real pipeline ([[Data-Pipeline]]).

## The bridge

- Swiss 58 m, 2-cell post-tensioned **box girder** motorway bridge.
- Instrumented Nov 1997 → Sep 1998: **1 year of ambient monitoring + staged progressive damage**.
- Sampling: **100 Hz, 27 channels** (acceleration + temperature).
- First modal modes ~3.5–4.5 Hz (Peeters & De Roeck 2001). The environmental paper has **>1,000 citations**.

## Progressive damage timeline (1998)

| Stage | Date |
|---|---|
| Pier settlement 20 → 95 mm | 10–18 Aug |
| Concrete spalling | 25–26 Aug |
| Hinge failure | 31 Aug |
| Anchor-head failure | 2–3 Sep |
| Tendon rupture | 7–9 Sep |

Honest lead time: first settlement → rupture ≈ **30 days**; spalling → rupture ≈ **15 days**. This N is measured on screen, never "18" ([[Storyboard]]).

## Processed mirror (use this, not the portal)

- `huggingface.co/datasets/thanglexuan/Z24-dataset-processed` (mirror `Sagarr123/Z24-dataset-processed`)
- `inputs.npy` **shape (1530, 27, 6000)** float64 m/s² · `labels.npy` **shape (1530,)** · ~**992 MB** · MIT license
- 17 scenarios × 9 setups × 10 segments. Each 60-s recording = 10 × 6000-sample segments.
- ⚠️ Download via **direct resolve URLs**, NOT `load_dataset()` (ConfigNamesError).

## Healthy vs damage labels

- Healthy: scenarios 1–7 (ambient/operational) + reference runs.
- Damage: staged pier settlement, spalling, hinge/anchor-head/tendon rupture → per-scenario labels for the confusion matrix ([[Metrics]]).
- 100 Hz → **10.24 s window = 1024 samples**; segment = 6000 samples ≈ 60 s.

## Licensing & caveats

- Official portal (bwk.kuleuven.be/bwm/z24) requires **registration review** — register and keep the confirmation email.
- License: KU Leuven research, **non-commercial, no third-party transfer** — disclose in [[QandA-Prep]] Q4.
- **Thermal drift trap:** modal frequencies swing ~10% with season vs ~1–2% for damage → temperature compensation is mandatory ([[Vibration-Model]], [[Key-Decisions]] #5).

Related: [[Datasets]] · [[Verified-Facts]] · [[Vibration-Model]]
