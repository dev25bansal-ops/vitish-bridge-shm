"""
cv/train_yolo.py — train a YOLO segmentation model on the crack dataset.

    python models/cv/train_yolo.py --model yolov8s-seg.pt --data data/cv/yolo/data.yaml \
        --epochs 50 --imgsz 512

Model selection: pass any ultralytics-compatible model id/weights path.
`--model auto` tries, in order: yolov8s-seg.pt, yolo11s-seg.pt, yolo26s-seg.pt
(whichever ultralytics can load first — it will download pretrained weights the
first time network is available). If a local `crack_seg.pt`/`best.pt` already
exists, it is used to resume.

The best checkpoint is copied to models/weights/crack_seg.pt (the canonical
location cv/inference.py and the backend load from).

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
DEFAULT_DATA = REPO_ROOT / "data" / "cv" / "yolo" / "data.yaml"

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train YOLO-seg crack detector")
    ap.add_argument("--model", default="yolov8s-seg.pt",
                    help="model id/weights (default yolov8s-seg.pt; 'auto' probes candidates)")
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=512)
    ap.add_argument("--batch", type=int, default=8)
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
        model_id = _pick_model(_MODEL_CANDIDATES)
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
                name="crack_seg", verbose=True)

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
