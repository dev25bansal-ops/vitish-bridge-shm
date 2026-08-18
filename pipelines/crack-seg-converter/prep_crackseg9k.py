"""
cv/prep_crackseg9k.py — convert the CC0 CrackSeg9k parquet set to YOLO-seg
format so ultralytics can train on it.

    python models/cv/prep_crackseg9k.py

Reads  data/cv/crackseg9k/{train,test}.parquet
  * image column  = base64-encoded 400x400 RGB PNG (the crack photo)
  * mask  column  = base64-encoded 400x400 L   PNG (soft/anti-aliased crack mask)
  * head  column  = 480x480 grayscale auxiliary image (ignored for training)

Writes data/cv/yolo9k/:
  images/train|val/{idx}.jpg
  labels/train|val/{idx}.txt   YOLO-seg polygon labels (class 0 'crack')
  data.yaml                    pointing at the split above

The dataset's own split is kept: train.parquet (7,332) -> train, test.parquet
(1,827) -> val, so there is no train/val leakage by construction.

Mask binarization: masks are soft-edged (anti-aliased grayscale); we threshold at
127 (half-intensity) to recover the core crack footprint, then find outer
contours, simplify with approxPolyDP, drop noise contours (< 15 px), and cap at
a sane number of polygon points per contour (ultralytics label limit).
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import cv2
import numpy as np
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "cv" / "crackseg9k"
OUT = REPO_ROOT / "data" / "cv" / "yolo9k"

MASK_THRESH = 127      # binarize soft mask at half-intensity
MIN_AREA = 15          # px — drop specks/contour noise (thin-crack tolerant)
MAX_POINTS = 256       # per-contour polygon point cap
EPS_FACTOR = 0.0012    # approxPolyDP epsilon as fraction of contour length
DILATE = 1             # 3x3 dilations before contouring (joins thin cracks)


def decode_b64(b64: str) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8),
                        cv2.IMREAD_COLOR)


def mask_to_polygons(mask_bin: np.ndarray) -> list[np.ndarray]:
    """Return list of [N,1,2] float32 polygons in normalized YOLO coords."""
    contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < MIN_AREA:
            continue
        epsilon = EPS_FACTOR * cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, epsilon, True)
        if len(approx) < 4:
            continue
        if len(approx) > MAX_POINTS:
            # keep the strongest points by distance resample (uniform sampling)
            idx = np.linspace(0, len(approx) - 1, MAX_POINTS).astype(int)
            approx = approx[idx]
        polys.append(approx)
    return polys


def row_to_yolo(r: dict) -> tuple[np.ndarray, list[np.ndarray]] | None:
    img = decode_b64(r["image"])
    mask_bin = cv2.imdecode(np.frombuffer(base64.b64decode(r["mask"]), np.uint8),
                            cv2.IMREAD_GRAYSCALE)
    if img is None or mask_bin is None:
        return None
    mask_bin = (mask_bin > MASK_THRESH).astype(np.uint8) * 255
    if DILATE:
        mask_bin = cv2.dilate(mask_bin, np.ones((3, 3), np.uint8), iterations=DILATE)
    polys = mask_to_polygons(mask_bin)
    if not polys:
        return None
    # ROADMAP line 66: normalize against the MASK's own size (ih, iw) — the
    # dead h/w params claimed the image is always 400x400, but the mask is the
    # authority for its own polygon coordinates.
    ih, iw = mask_bin.shape[:2]
    norm = []
    for p in polys:
        xy = p.reshape(-1, 2).astype(np.float64)
        xy[:, 0] /= iw
        xy[:, 1] /= ih
        xy = xy.clip(0.0, 1.0)
        norm.append(xy)
    return img, norm


def write_yolo(img: np.ndarray, polys: list[np.ndarray], img_path: Path,
               label_path: Path) -> int:
    img_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(img_path), img)
    if not ok:
        return 0
    lines = []
    for xy in polys:
        line = "0 " + " ".join(f"{v:.6f}" for v in xy.reshape(-1))
        lines.append(line)
    label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def convert(split_name: str, parquet_name: str, out_sub: str) -> tuple[int, int]:
    pf = pq.ParquetFile(SRC / parquet_name)
    n_rows = pf.metadata.num_rows
    img_dir = OUT / "images" / out_sub
    lbl_dir = OUT / "labels" / out_sub
    ok = 0
    skipped = 0
    batch = pf.iter_batches(batch_size=512)
    idx = 0
    for table in batch:
        for rec in table.to_pylist():
            res = row_to_yolo(rec)
            if res is None:
                skipped += 1
                idx += 1
                continue
            img, polys = res
            n_poly = write_yolo(img, polys,
                                img_dir / f"{idx:05d}.jpg",
                                lbl_dir / f"{idx:05d}.txt")
            if n_poly == 0:
                skipped += 1
            else:
                ok += 1
            idx += 1
        print(f"  [crackseg9k] {split_name}: {idx}/{n_rows} (ok={ok} skip={skipped})",
              flush=True)
    return ok, skipped


def write_data_yaml() -> None:
    yaml = (
        "# YOLO-seg dataset derived from CrackSeg9k (CC0 1.0). "
        "Generated by models/cv/prep_crackseg9k.py\n"
        f"path: {str(OUT)}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: crack\n"
    )
    (OUT / "data.yaml").write_text(yaml, encoding="utf-8")


def main() -> int:
    if not (SRC / "train.parquet").exists() or not (SRC / "test.parquet").exists():
        print(f"ERROR: CrackSeg9k parquet files not found under {SRC}.\n"
              "Download first (see vault/02-Research/Datasets.md).", file=sys.stderr)
        return 1
    print("converting CrackSeg9k -> YOLO-seg at", OUT)
    t_ok, t_skip = convert("train", "train.parquet", "train")
    v_ok, v_skip = convert("val", "test.parquet", "val")
    write_data_yaml()
    print(f"\nDONE: train ok={t_ok} skip={t_skip} | val ok={v_ok} skip={v_skip}")
    print(f"data.yaml at {OUT / 'data.yaml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
