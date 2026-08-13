---
tags: [research, datasets, ml, vitish-2026, shm]
created: 2026-08-13
---

# Datasets — confirmed live, download before H0

| Dataset | What it is | Size / License | Where | Gotcha |
|---|---|---|---|---|
| **CrackSeg9k** | 9,255-img crack segmentation (Crack500/DeepCrack/CrackTree/GAPS/Masonry/Rissbilder) | **9,159 rows** (train 7,332 + test 1,827) × 400² img+mask · ~4.2 GB · **CC0 1.0** | HF `rimvydasrub/crackseg9k` — exactly 2 parquet files (`data/train.parquet` 3.36GB, `data/test.parquet` 0.84GB), cols `image`/`mask`/`head` | **DOWNLOADED ✓ 2026-08-13** → `data/cv/crackseg9k/`. Image/mask columns are **base64-encoded PNG strings** (decode with `base64.b64decode`). Advertised 9,255 is approximate — verified row count 9,159. Only permissive large crack-seg set (CC0) |
| **Hell Bridge Test Arena (HBTA)** | Full-scale steel bridge, imposed damage, **100 Hz** accel | **2.5 GB** single HDF5 + loader (`main.py`/`functions.py`) · **CC-BY-4.0** | Zenodo `14632942` | **DOWNLOADED ✓ 2026-08-13** → `data/vib/hbta/`. 30+ scenarios `MVS_P{1,2}_DS{1..8}_SM_{Y,Z}_01` (damage states) + `MVS_P1_UDS_SM_{Y,Z}_0{1,2}` (undamaged), 15 AG channels, 62,221 samples ea. Directly validates the LSTM-AE / healthy-envelope arc with ground-truth damage |
| **Z24 processed mirror** | Z24 benchmark, `inputs (1530,27,6000)` + `labels (1530,)` | ~992 MB · MIT | HF `thanglexuan/Z24-dataset-processed` (mirror `Sagarr123/…`) | Direct resolve URLs only, not `load_dataset()`. Official portal needs registration. See [[Z24-Benchmark]] |
| **dacl10k** | Bridge damage segmentation, WACV 2024 (Flotzinger et al., arXiv:2309.00460) | ~9,920 imgs · 512² · ~5 GB · **CC BY-NC 4.0** | HF `Voxel51/dacl10k` + `phiyodr/dacl10k-toolkit` | **DOWNLOADED ✓ 2026-08-13** via `scripts/download_dacl10k.py` — **8,922/8,922 files verified (fail=0)**, 18–19 classes, **multi-label semantic** (best mIoU **0.42**), imbalanced; non-commercial — dev/benchmark only, disclose in [[QandA-Prep]] |
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
