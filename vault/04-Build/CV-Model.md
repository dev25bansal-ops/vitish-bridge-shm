---
tags: [build, cv, ml, vitish-2026, shm]
created: 2026-08-13
---

# CV — binary crack segmentation

Component 2 of 4. The primary build inside the 36 h.

## Data prep

- **SDNET2018** (56,000 × 256² binary crack/no-crack, balanced) — classification/pretraining head only, **no masks** ([[Datasets]]).
- **crack-only dacl10k subset** for segmentation fine-tune: convert **semantic masks → connected-component → instance masks** (COCO/RLE → single-label YOLO-seg polygons). Multi-label overlap breaks YOLO's single-label assumption — hence binary-only.
- Split: **70/20/10**; report **measured mAP@0.5** on your own split — do NOT state 0.65 as fact (best published dacl10k is mIoU 0.42).

## Training

- **YOLO26s-seg** (Jan 2026, +2.2 mask mAP over v8s); YOLO11s as fallback. One-line swap in Ultralytics.
- Fine-tune @ imgsz 512, ~50–100 epochs on one RTX 3060/4060-class GPU ≈ 2–4 h (H2–H6 in [[36h-Build-Plan]]).
- Frozen backbone → fine-tune → evaluate on curated demo frames with visible cracks.
- Pre-hackathon (optional): full dacl10k 19-class fine-tune for the talking point.

## Mask pipeline (be ready to explain)

- dacl10k: semantic → connected-component → instance masks for YOLO-seg.
- SDNET2018: no masks → classification/pretraining only.
- Optional **SAM2 refinement pass** (SECrackSeg S-Adapter, Sensors 2025) for hero masks.

## Fallbacks (zero training)

- **Ultralytics crack-seg** weights (91.6 MB, guaranteed 2-h baseline).
- Any verified HF pretrained crack model.

## Judge defense

- "Why not just SAM2 out of the box?" → zero-shot foundation models plateau on real infrastructure (CiF, arXiv:2605.18413, ~25% mAP); we fine-tune on bridge-specific data.
- "Why not YOLO12?" → we use YOLO26s (2026), neutralized.

Related: [[Datasets]] · [[Academic-SOTA]] · [[Metrics]] · [[System-Architecture]]
