# CV metric sheet — crack_seg

Model: `yolo-seg (crack_seg.pt, conf=0.001)`

| metric | value |
|---|---|
| mAP@0.5 (full PR curve, conf 0.001) | 0.0826 |
| precision @ conf 0.25 (shipped) | 0.4256 |
| recall @ conf 0.25 (shipped) | 0.057 |
| F1 @ conf 0.25 (shipped) | 0.1005 |
| image-level recall @ 0.25 | 0.9747 (500/513) |
| images / GT boxes / detections | 741 / 2913 / 156448 |

mAP@0.5 is computed over the FULL precision-recall curve (detections down to conf 0.001, sorted by confidence, 101-point interpolation) — the standard protocol. Independent cross-check: ultralytics `model.val()` on the same split reports box mAP@0.5 = 0.074. The @0.25 columns are the SHIPPED operating point of `CrackDetector`: a strict threshold chosen to keep clean frames FP-free (pinned demo policy), which trades box-level recall. Image-level recall = fraction of cracked val images with ≥ 1 IoU-matched detection, the narrative metric `verify_crack_seg.py` uses — the demo's 'did we catch the cracked frame' question.

Split: yolo9k_sub2 val (CC0 CrackSeg9k-derived negatives-balanced subset — the model's OWN training split; a sanity floor, not a cross-domain claim). GT = YOLO polygon labels converted to boxes; IoU ≥ 0.5 matching; single 'crack' class.