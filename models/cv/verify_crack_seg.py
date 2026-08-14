"""
cv/verify_crack_seg.py — verify the trained crack_seg.pt against the Canny
heuristic on real images.

    python models/cv/verify_crack_seg.py [--n-cracked 40] [--n-clean 20]

Two legs, each run in BOTH detector modes (YOLO-seg when models/weights/
crack_seg.pt exists, else the pure-OpenCV heuristic) so we can prove the
trained model beats the heuristic — the honest claim we make at the demo:

  * Cracked leg  : N images sampled from data/cv/yolo9k/images/val (real CC0
                   crack photos with known crack polygons). Metric = recall
                   (frac of images with >=1 detection) + mean conf/severity.
  * Clean leg     : N uncracked SDNET2018 tiles (UD/UP/UW). The model must NOT
                   flag clean concrete. Metric = false-positive rate + mean
                   severity (must stay low so cv never jumps -> no GREEN
                   flicker).

Honesty notes:
  * SDNET2018 is registration-gated, dev-only — used here purely as a LOCAL
    validation set for the false-positive check, never shipped/production.
  * Val images are CC0 CrackSeg9k-derived (same source as training) — recall on
    them is a sanity floor, not a cross-domain claim.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "models" / "cv") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "models" / "cv"))

from inference import CrackDetector  # noqa: E402

YOLO9K_VAL = REPO_ROOT / "data" / "cv" / "yolo9k" / "images" / "val"
SDNET_ROOT = REPO_ROOT / "data" / "cv" / "sdnet2018"
WEIGHTS = REPO_ROOT / "models" / "weights" / "crack_seg.pt"


def _sample(paths: list[Path], n: int, seed: int = 0) -> list[Path]:
    rng = random.Random(seed)
    return rng.sample(paths, min(n, len(paths)))


def _cracked_images(n: int) -> list[Path]:
    if not YOLO9K_VAL.exists():
        print(f"  [verify] WARN: {YOLO9K_VAL} missing — cracked leg skipped")
        return []
    return _sample(sorted(YOLO9K_VAL.glob("*.jpg")), n)


def _clean_images(n: int) -> list[Path]:
    if not SDNET_ROOT.exists():
        print(f"  [verify] WARN: {SDNET_ROOT} missing — clean leg skipped")
        return []
    cands = sorted(p for p in SDNET_ROOT.glob("*/*/*.jpg")
                   if p.parts[-2] in ("UD", "UP", "UW"))
    return _sample(cands, n)


def run_leg(det: CrackDetector, paths: list[Path], name: str) -> dict:
    n_det_img, max_conf, max_sev, total_area, n_img = 0, 0.0, 0.0, 0, len(paths)
    for p in paths:
        img = cv2.imread(str(p))
        if img is None:
            n_img -= 1
            continue
        dets = det.detect(img)
        if dets:
            n_det_img += 1
            max_conf = max(max_conf, max(d["conf"] for d in dets))
            max_sev = max(max_sev, max(d["severity"] for d in dets))
            total_area += sum(d["area_px"] for d in dets)
    n_img = max(n_img, 0)
    return {
        "name": name, "n": n_img,
        "recall": (n_det_img / n_img) if n_img else float("nan"),
        "max_conf": round(max_conf, 3),
        "max_sev": round(max_sev, 4),
        "mean_sev": round(total_area / max(1, n_img) /
                          max(1, 0.05 * 400 * 400), 4),
    }


def fmt(r: dict) -> str:
    return (f"  {r['name']:<28} n={r['n']:>3}  recall={r['recall']:.2f}  "
            f"max_conf={r['max_conf']:.2f}  max_sev={r['max_sev']:.3f}  "
            f"mean_sev={r['mean_sev']:.3f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify crack_seg.pt vs heuristic")
    ap.add_argument("--n-cracked", type=int, default=40)
    ap.add_argument("--n-clean", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    cracked = _cracked_images(args.n_cracked)
    clean = _clean_images(args.n_clean)
    print(f"cracked={len(cracked)} clean={len(clean)}")

    print("\n=== YOLO mode (trained crack_seg.pt) ===")
    yolo = CrackDetector(weights_path=WEIGHTS)
    yc = run_leg(yolo, cracked, "yolo/cracked")
    ycl = run_leg(yolo, clean, "yolo/clean")
    print(fmt(yc))
    print(fmt(ycl))

    print("\n=== heuristic mode (Canny fallback) ===")
    heur = CrackDetector(weights_path=Path("no_such_weights.pt"))
    hc = run_leg(heur, cracked, "heuristic/cracked")
    hcl = run_leg(heur, clean, "heuristic/clean")
    print(fmt(hc))
    print(fmt(hcl))

    # ---- verdicts ----------------------------------------------------------
    ok = True
    if yc["n"]:
        beats_recall = yc["recall"] >= hc["recall"]
        print(f"\n[cracked recall] YOLO {yc['recall']:.2f} vs heuristic "
              f"{hc['recall']:.2f} -> {'PASS' if beats_recall else 'FAIL'}")
        ok &= beats_recall
    if ycl["n"]:
        fp_ok = ycl["max_sev"] <= 0.15
        print(f"[clean FP] YOLO max_sev {ycl['max_sev']:.3f} "
              f"(must be <= 0.15 to avoid cv jump) -> "
              f"{'PASS' if fp_ok else 'FAIL'}")
        ok &= fp_ok
        if hcl["n"]:
            beats_fp = ycl["max_sev"] <= hcl["max_sev"]
            print(f"[clean FP] YOLO {ycl['max_sev']:.3f} vs heuristic "
                  f"{hcl['max_sev']:.3f} -> {'PASS' if beats_fp else 'FAIL'}")
            ok &= beats_fp

    print(f"\nVERIFY RESULT: {'PASS' if ok else 'FAIL'} "
          f"(mode={yolo.mode.split('(')[0].strip()})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
