"""
cv/train_unet.py — train a compact U-Net crack segmenter (dense BCE+Dice).

    python models/cv/train_unet.py [--epochs 50] [--imgsz 256] [--batch 32]

WHY a U-Net (not YOLO-seg): crack-seg experiments on CrackSeg9k showed the
YOLO-seg path is structurally capped for hairline cracks —
  * the seg head's mask resolution can't represent 1-3 px cracks (mAP50-95 ~0.05),
  * with no negative images the classifier learns "every concrete image is
    cracked" (90% FP on clean tiles even at conf 0.8, and adding 907 negatives
    did not fix it).
A dense U-Net predicts a per-pixel crack probability, so thin cracks are not
quantized into polygons, and the negatives (clean concrete, empty masks) train
the "no crack" class directly. Output is a real crack-area fraction — an
honest, measured signal for the BHI cv sub-index.

Data: yolo9k_sub2 (2,062 cracked + 907 clean-negative crops, 100% CC0).
Each label is rasterized back to a 400x400 mask, then the image+mask pair is
resized to --imgsz. Images whose label is empty are pure-background negatives.

Loss: BCEWithLogits + Dice (classic for thin structures).
Augmentation: flips/rot90/light color jitter — deliberately NOT mosaic/mixup,
which smear thin cracks.

Output: models/weights/crack_unet.pt (state_dict) + a printed eval table
(Dice / IoU on val positives, FP-rate + max crack-fraction on negatives).
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data" / "cv" / "yolo9k_sub2"
OUT = REPO_ROOT / "models" / "weights" / "crack_unet.pt"

SEED = 0


# ------------------------------------------------------------------ U-Net
class _ConvBn(nn.Module):
    def __init__(self, cin: int, cout: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(cin, cout, 3, padding=1, bias=False),
            nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
            nn.Conv2d(cout, cout, 3, padding=1, bias=False),
            nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class CrackUNet(nn.Module):
    """Compact encoder-decoder for dense crack probability (Sigmoid output)."""

    def __init__(self, in_ch: int = 3) -> None:
        super().__init__()
        e = [32, 64, 128, 256]
        self.e1 = _ConvBn(in_ch, e[0])
        self.e2 = _ConvBn(e[0], e[1])
        self.e3 = _ConvBn(e[1], e[2])
        self.e4 = _ConvBn(e[2], e[3])
        self.pool = nn.MaxPool2d(2)
        self.bott = _ConvBn(e[3], e[3] * 2)

        self.d4 = _ConvBn(e[3] * 2 + e[3], e[3])
        self.d3 = _ConvBn(e[3] + e[2], e[2])
        self.d2 = _ConvBn(e[2] + e[1], e[1])
        self.d1 = _ConvBn(e[1] + e[0], e[0])
        self.head = nn.Conv2d(e[0], 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        c1 = self.e1(x)
        c2 = self.e2(self.pool(c1))
        c3 = self.e3(self.pool(c2))
        c4 = self.e4(self.pool(c3))
        b = self.bott(self.pool(c4))

        u4 = F.interpolate(b, scale_factor=2, mode="bilinear", align_corners=False)
        d4 = self.d4(torch.cat([u4, c4], 1))
        u3 = F.interpolate(d4, scale_factor=2, mode="bilinear", align_corners=False)
        d3 = self.d3(torch.cat([u3, c3], 1))
        u2 = F.interpolate(d3, scale_factor=2, mode="bilinear", align_corners=False)
        d2 = self.d2(torch.cat([u2, c2], 1))
        u1 = F.interpolate(d2, scale_factor=2, mode="bilinear", align_corners=False)
        d1 = self.d1(torch.cat([u1, c1], 1))
        return self.head(d1)


def dice_loss(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Soft Dice loss on logits (after sigmoid). target is {0,1}."""
    prob = torch.sigmoid(logits)
    smooth = 1.0
    inter = (prob * target).sum(dim=(1, 2, 3))
    union = prob.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    return 1.0 - (2.0 * inter + smooth) / (union + smooth)


# ------------------------------------------------------------------ data
def _rasterize(label_txt: Path, h: int = 400, w: int = 400) -> np.ndarray:
    m = np.zeros((h, w), np.uint8)
    if not label_txt.exists() or label_txt.stat().st_size < 4:
        return m
    for line in label_txt.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 9:
            continue
        xy = np.array([float(v) for v in parts[1:]]).reshape(-1, 2)
        xy[:, 0] *= w
        xy[:, 1] *= h
        import cv2
        cv2.fillPoly(m, [xy.astype(np.int32)], 1)
    return m


class CrackDataset(Dataset):
    """Images + crack masks, all PRELOADED into RAM so the training hot path
    is pure indexing + augmentation (no per-item disk read or resize).

    RAM: 2 * imgsz^2 bytes per image (1 uint8 image + 1 uint8 mask), i.e.
    ~0.9 GiB for the 2,969-image train split at imgsz 256 — fine on this
    laptop, and it removes the num_workers headache on Windows (no fork).
    """

    def __init__(self, split: str, imgsz: int, train: bool) -> None:
        import cv2
        self.imgsz = imgsz
        self.train = train
        img_dir = DATA / "images" / split
        lbl_dir = DATA / "labels" / split
        pairs = sorted(p for p in img_dir.glob("*.jpg"))
        self.neg_idx = [i for i, p in enumerate(pairs)
                        if (lbl_dir / (p.stem + ".txt")).stat().st_size < 4]
        self.images = np.zeros((len(pairs), imgsz, imgsz, 3), np.uint8)
        self.masks = np.zeros((len(pairs), imgsz, imgsz), np.uint8)
        for i, p in enumerate(pairs):
            img = cv2.imread(str(p))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            self.images[i] = cv2.resize(img, (imgsz, imgsz))
            self.masks[i] = cv2.resize(_rasterize(lbl_dir / (p.stem + ".txt")),
                                       (imgsz, imgsz),
                                       interpolation=cv2.INTER_NEAREST)
        self.rng = random.Random(SEED)

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, i: int):
        img = self.images[i].copy()
        m = self.masks[i].copy()
        if self.train:
            if self.rng.random() < 0.5:
                img = img[:, ::-1]; m = m[:, ::-1]
            if self.rng.random() < 0.5:
                img = img[::-1]; m = m[::-1]
            k = self.rng.choice([1, 2, 3])
            if k != 4:
                img = np.rot90(img, k); m = np.rot90(m, k)
            # light color jitter (thin-crack-safe)
            if self.rng.random() < 0.5:
                f = self.rng.uniform(0.85, 1.15)
                img = np.clip(img.astype(np.float32) * f, 0, 255).astype(np.uint8)
        img = torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1).float() / 255.0
        m = torch.from_numpy(np.ascontiguousarray(m)).float().unsqueeze(0)
        return img, m


# ------------------------------------------------------------------ train
def _epoch(model, loader, opt, device, train: bool):
    model.train(train)
    tot_bce = tot_dice = n = 0.0
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        with torch.set_grad_enabled(train):
            logits = model(x)
            bce = F.binary_cross_entropy_with_logits(logits, y)
            dice = dice_loss(logits, y).mean()
            loss = bce + dice
            if train:
                opt.zero_grad()
                loss.backward()
                opt.step()
        tot_bce += bce.item() * len(x)
        tot_dice += dice.item() * len(x)
        n += len(x)
    return tot_bce / n, tot_dice / n


def _eval(model, ds, device, imgsz: int):
    """Return (dice, iou, fp_rate, neg_max_crack_frac) on the whole split."""
    model.eval()
    dices, ious, fps, neg_fracs = [], [], [], []
    with torch.no_grad():
        for i in range(len(ds)):
            x, y = ds[i]
            x = x.unsqueeze(0).to(device)
            prob = torch.sigmoid(model(x))[0, 0].cpu().numpy()
            pred = (prob > 0.5).astype(np.uint8)
            gt = ds.masks[i] > 0  # already at imgsz resolution
            if gt.sum() == 0:  # negative image
                fps.append(int(pred.sum() > 0))
                neg_fracs.append(float((prob > 0.5).mean()))
            else:
                inter = (pred & gt).sum()
                union = (pred | gt).sum()
                if union:
                    ious.append(inter / union)
                    dices.append(2 * inter / (pred.sum() + gt.sum() + 1))
    return (np.mean(dices) if dices else float("nan"),
            np.mean(ious) if ious else float("nan"),
            np.mean(fps) if fps else float("nan"),
            max(neg_fracs) if neg_fracs else 0.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train U-Net crack segmenter")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=256)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--device", default=None)
    args = ap.parse_args(argv)

    if not (DATA / "images" / "train").exists():
        print(f"ERROR: dataset not found at {DATA} — run prep_negatives.py first.",
              file=sys.stderr)
        return 1
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    random.seed(SEED)
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device={device}  imgsz={args.imgsz}  batch={args.batch}  "
          f"epochs={args.epochs}")

    train_ds = CrackDataset("train", args.imgsz, train=True)
    val_ds = CrackDataset("val", args.imgsz, train=False)
    print(f"train={len(train_ds)} (neg={len(train_ds.neg_idx)})  "
          f"val={len(val_ds)} (neg={len(val_ds.neg_idx)})", flush=True)
    loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True,
                        num_workers=0, drop_last=True)

    model = CrackUNet().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    print(f"params={sum(p.numel() for p in model.parameters())/1e6:.2f}M")

    best_dice = -1.0
    t0 = time.time()
    for ep in range(1, args.epochs + 1):
        tb, td = _epoch(model, loader, opt, device, train=True)
        sched.step()
        el = time.time() - t0
        print(f"ep {ep:3d}  bce={tb:.4f} dice={td:.4f}  [{el:.0f}s]", flush=True)
        if ep % 5 == 0 or ep == 1:
            dice, iou, fp, nfr = _eval(model, val_ds, device, args.imgsz)
            print(f"      val_dice={dice:.3f} val_iou={iou:.3f} "
                  f"fp_neg={fp:.3f} neg_maxfrac={nfr:.4f}", flush=True)
            if dice == dice and dice > best_dice:  # not NaN
                best_dice = dice
                torch.save(model.state_dict(), OUT)
                print(f"      -> saved {OUT} (dice {dice:.3f})", flush=True)
    if best_dice < 0:
        torch.save(model.state_dict(), OUT)
    print(f"\nDONE in {time.time()-t0:.0f}s  best_val_dice={best_dice:.3f}")
    print(f"weights: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
