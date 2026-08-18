#!/usr/bin/env python
"""Build the committed real-Z24 fixture for the trained-ML gates (TEST-F3).

The trained gates (`test_trained_path.py` §4, `test_deconfounding.py` LEG C)
assert real healthy-vs-damaged separation on the SHIPPED ensemble.  On a fresh
clone / CI the full `data/z24/inputs.npy` (991 MB) is gitignored, so those
assertions silently never ran outside the trainer machine.  This script samples
a SMALL, deterministic slice of the real benchmark — 180 windows (1024 samples,
channels 6/7/8) per group, real float32 Z24 data — and commits it under
`data/z24/fixture/` (~2.9 MB) so the gates exercise real Z24 evidence everywhere.

Regenerate (only when you have the full file) with:

    python scripts/make_z24_fixture.py --n-seg 12

The committed fixture is the shipped evidence; a regenerated fixture is a
different (still-real) sample and the gates' bounds must be re-measured on it.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

# Resolve the repo root whether this runs from scripts/ or from this package.
# (paths[2] = D:\SHM_Bridges when invoked from pipelines/z24-mirror/)
_path = Path(__file__).resolve()
REPO_ROOT = _path.parents[2] if (_path.name == "make_z24_fixture.py" and _path.parent.name == "z24-mirror") else _path.parents[1]
Z24 = REPO_ROOT / "data" / "z24" / "inputs.npy"
Z24_LABELS = Z24.with_name("labels.npy")
FIXTURE_DIR = Z24.parent / "fixture"
W = 1024
CHANNELS = (6, 7, 8)


def _windows_for_labels(arr, lab, labels: list[int], n_seg: int) -> np.ndarray:
    """Sample `n_seg` segments TOTAL (round-robin across `labels`) so a group
    never bloats with one label's tail.  Returns W-windows (float32)."""
    out = []
    taken = 0
    # round-robin over labels until n_seg segments are collected
    while taken < n_seg:
        progressed = False
        for target in labels:
            idx = np.where(lab == target)[0]
            if idx.size == 0:
                continue
            s = int(idx[taken % idx.size])
            for c in CHANNELS:
                row = arr[s, c]
                for i in range(0, 6000 - W + 1, W):
                    out.append(row[i:i + W])
            taken += 1
            progressed = True
            if taken >= n_seg:
                break
        if not progressed:
            raise SystemExit(f"no segments found for labels {labels}")
    return np.stack(out).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-seg", type=int, default=12,
                    help="segments sampled per label (default 12 -> 180 windows)")
    args = ap.parse_args()
    if not (Z24.exists() and Z24_LABELS.exists()):
        raise SystemExit(f"full Z24 file absent ({Z24}) — nothing to sample")
    arr = np.load(Z24, mmap_mode="r")
    lab = np.load(Z24_LABELS).ravel()
    # Per-label groups so the gates can assert the envelope's OWN healthy state
    # (label 0) separately from healthy states it does NOT span (labels 1 and 6 —
    # the documented state-confounding finding the fixture surfaces).
    damaged_labels = [2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    groups = {
        "healthy0.npy": _windows_for_labels(arr, lab, [0], args.n_seg),
        "healthy1.npy": _windows_for_labels(arr, lab, [1], args.n_seg),
        "label6.npy": _windows_for_labels(arr, lab, [6], args.n_seg),
        "damaged.npy": _windows_for_labels(arr, lab, damaged_labels, args.n_seg),
    }
    for name, w in groups.items():
        np.save(FIXTURE_DIR / name, w)
        print(f"  wrote data/z24/fixture/{name}  shape={w.shape}  "
              f"{w.nbytes / 1e6:.2f} MB")
    total = sum(w.nbytes for w in groups.values()) / 1e6
    print(f"fixture total {total:.2f} MB (real Z24 float32 windows, channels "
          f"{'/'.join(map(str, CHANNELS))}, W={W})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
