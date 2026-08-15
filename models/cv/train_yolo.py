"""
cv/train_yolo.py — train a YOLO segmentation model on the crack dataset.

    python models/cv/train_yolo.py --model yolov8s-seg.pt --data data/cv/yolo/data.yaml \
        --epochs 50 --imgsz 512

Model selection: pass any ultralytics-compatible model id/weights path.
`--model auto` tries, in order: yolov8s-seg.pt, yolo11s-seg.pt, yolo26s-seg.pt
(whichever ultralytics can load first — it will download pretrained weights the
first time network is available). If a local `models/weights/crack_seg.pt` (or
a `best.pt` under `models/weights/yolo_runs/`) already exists, it is used to
RESUME instead of downloading — so retraining works on an offline machine
(ROADMAP line 64).  Pass `--model <id|path>` explicitly to force a pretrained
base instead of the local weights.

The best checkpoint is copied to models/weights/crack_seg.pt (the canonical
location cv/inference.py and the backend load from).

Data default (ROADMAP line 64): data/cv/yolo9k_sub2/data.yaml — the
negatives-balanced 1/3 CrackSeg9k subset (2,062 cracked + 907 clean-negative
crops, 100% CC0).  Bare retrains must NOT hit the all-positives set
(data/cv/yolo/data.yaml), whose FP bias makes the model flag every concrete
image.  `--data` overrides.

Guards:
  * ultralytics missing -> clear message, non-zero exit (no crash).
  * data.yaml missing -> auto-generates a small synthetic set via prep_sdnet so
    the training loop is always exercisable.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS = REPO_ROOT / "models" / "weights"
# ROADMAP line 64: negatives-balanced set is the default; the bare all-positives
# yolo/data.yaml is FP-biased (every concrete image = cracked).
DEFAULT_DATA = REPO_ROOT / "data" / "cv" / "yolo9k_sub2" / "data.yaml"

_MODEL_CANDIDATES = ["yolov8s-seg.pt", "yolo11s-seg.pt", "yolo26s-seg.pt"]


def _pick_model(candidates: list[str]) -> str:
    """Return the first model ultralytics can actually load."""
    from ultralytics import YOLO
    for cand in candidates:
        try:
            YOLO(cand)  # instantiates (and downloads weights if needed)
            print(f"  [yolo] using model: {cand}")
            return cand
        except Exception as exc:
            print(f"  [yolo] could not load {cand}: {exc}")
    raise RuntimeError("none of the candidate seg models could be loaded; "
                       "pass --model <local weights path>")


def _local_resume_path(outdir: Path) -> Path | None:
    """Return a local weights path to resume from, or None.

    ROADMAP line 64: the canonical `crack_seg.pt` wins, else the most recent
    `best.pt` under yolo_runs/.  This is what makes retraining work offline —
    a stock `--model yolov8s-seg.pt` would otherwise fail to download.
    """
    for cand in (outdir / "crack_seg.pt",
                 *sorted((outdir / "yolo_runs").glob("*/weights/best.pt"))):
        if cand.exists():
            return cand
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train YOLO-seg crack detector")
    ap.add_argument("--model", default="yolov8s-seg.pt",
                    help="model id/weights (default yolov8s-seg.pt; 'auto' probes candidates)")
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=512)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=8,
                    help="dataloader workers (laptops w/ <16GB RAM: use 2-4 to "
                         "avoid pagefile thrash from worker prefetch caches)")
    ap.add_argument("--cache", action="store_true",
                    help="RAM-cache decoded images (fast epochs, needs "
                         "~n_imgs*imgsz^2*3 bytes; omit on low-RAM boxes)")
    ap.add_argument("--device", default=None, help="'0','cpu', etc. (default: auto)")
    ap.add_argument("--outdir", default=str(DEFAULT_WEIGHTS))
    args = ap.parse_args(argv)

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        print(f"ERROR: ultralytics is not installed ({exc}).\n"
              "CV training requires ultralytics. The demo can still run the\n"
              "Canny/contour heuristic fallback in cv/inference.py.\n"
              "Install with: pip install ultralytics   (allowed once per environment)",
              file=sys.stderr)
        return 2

    data = Path(args.data)
    if not data.exists():
        print(f"  [yolo] data.yaml '{data}' not found -> generating a synthetic "
              "crack set so training is exercisable.")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from prep_sdnet import generate_synthetic_crack_dataset
        data = generate_synthetic_crack_dataset(data.parent, n_train=40, n_val=12, seed=0)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    project = outdir / "yolo_runs"

    model_id = args.model
    if model_id == "auto":
        # ROADMAP line 64: prefer local weights over downloading a pretrained
        # base — 'auto' is a probe, and an offline machine can't download.
        local = _local_resume_path(outdir)
        if local is not None:
            print(f"  [yolo] --model auto: resuming from local weights {local}")
            model_id = str(local)
        else:
            model_id = _pick_model(_MODEL_CANDIDATES)
    elif model_id in _MODEL_CANDIDATES:
        # stock pretrained id requested; if a local crack_seg.pt already exists,
        # the docstring promises resume-from-local (and offline machines would
        # otherwise exit 3 on the failed download).  --model <explicit path>
        # still overrides.
        local = _local_resume_path(outdir)
        if local is not None:
            print(f"  [yolo] resuming from local weights {local} "
                  f"(pass --model {model_id} explicitly to force a "
                  "pretrained base)")
            model_id = str(local)
    try:
        model = YOLO(model_id)
    except Exception as exc:
        print(f"ERROR: could not load YOLO model '{model_id}' ({exc}).\n"
              "Check the model name/path, or pass --model auto to probe "
              "yolov8s-seg / yolo11s-seg / yolo26s-seg (needs network for the "
              "first download).", file=sys.stderr)
        return 3

    device = args.device
    if device is None:
        try:
            import torch
            device = "0" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"

    print(f"  [yolo] training {model_id} data={data} epochs={args.epochs} "
          f"imgsz={args.imgsz} device={device}")
    model.train(data=str(data), epochs=args.epochs, imgsz=args.imgsz,
                batch=args.batch, device=device, project=str(project),
                name="crack_seg", workers=args.workers, cache=args.cache,
                verbose=True)

    # best.pt -> canonical crack_seg.pt location
    best = project / "crack_seg" / "weights" / "best.pt"
    if not best.exists():
        # ultralytics may have used the run dir differently
        hits = list(project.glob("*/weights/best.pt"))
        if hits:
            best = hits[0]
    if best.exists():
        shutil.copy(best, outdir / "crack_seg.pt")
        print(f"  [yolo] saved {outdir / 'crack_seg.pt'}")
    else:
        print(f"  [yolo] WARNING: best.pt not found under {project}")
        return 1
    print("DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
