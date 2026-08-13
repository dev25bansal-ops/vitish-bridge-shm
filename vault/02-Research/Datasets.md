---
tags: [research, datasets, ml, vitish-2026, shm]
created: 2026-08-13
---

# Datasets — confirmed live, download before H0

| Dataset | What it is | Size / License | Where | Gotcha |
|---|---|---|---|---|
| **Z24 processed mirror** | Z24 benchmark, `inputs (1530,27,6000)` + `labels (1530,)` | ~992 MB · MIT | HF `thanglexuan/Z24-dataset-processed` (mirror `Sagarr123/…`) | Direct resolve URLs only, not `load_dataset()`. Official portal needs registration. See [[Z24-Benchmark]] |
| **dacl10k** | Bridge damage segmentation, WACV 2024 (Flotzinger et al., arXiv:2309.00460) | ~9,920 imgs · 512² · ~1.1 GB · **CC BY-NC 4.0** | HF + `phiyodr/dacl10k-toolkit` | 18–19 classes, **multi-label semantic** (best mIoU **0.42**), imbalanced; non-commercial — disclose in [[QandA-Prep]] |
| **SDNET2018** | Concrete crack / no-crack, **binary**, crack widths 0.06–25 mm | 56,000 × 256² · balanced | IEEE DataPort → `ieee-dataport.org/documents/sdnet2018-concrete-crack-image-dataset-machine-learning-applications` (verified live 200, 2026-08-13; `/open-access/` prefix 404s) | **Registration (free IEEE account) → manual download**. **DOWNLOADED ✓ 2026-08-13** (`E:\DNET2018.zip` 504 MB, integrity OK): cracked 8,487 (D 2,026 / W 3,852 / P 2,609) + uncracked 47,611, extracted to `data/cv/sdnet2018`. **No pixel masks** — classification/pretraining only; ~5.6:1 imbalance → subsample negatives |
| **Ultralytics crack-seg** | Official small crack segmentation set | 91.6 MB | Ultralytics assets | Guaranteed ~2-h baseline ([[CV-Model]]) |
| **Vänersborg (DiB, Sweden)** | 64 bridge openings | CC BY 4.0 · Zenodo 8300495 | KTH/IoTBridge | **No damage ground-truth labels** — reconstruction-error sanity check only, NOT cross-bridge F1 |
| **US NBI** | 624,193-bridge inventory (FHWA) | — | FHWA NBI | Use for the 50 real locations on the regulator map ([[Digital-Twin]]) |

## Download schedule (from [[Pre-Hackathon-Checklist]])

- Day −14: Z24 mirror (office WiFi), dacl10k v3, Z24 official .mat (register!)
- Day −7: SDNET2018, Vänersborg, US NBI coordinates
- Day −3: Ultralytics crack-seg

## Copy everything

All datasets + checkpoints to USB + cloud, verified with **network OFF** — zero network reliance at demo time.

Related: [[Z24-Benchmark]] · [[CV-Model]] · [[Vibration-Model]] · [[Data-Pipeline]]
