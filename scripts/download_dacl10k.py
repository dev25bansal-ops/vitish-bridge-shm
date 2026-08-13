"""
scripts/download_dacl10k.py — fetch the dacl10k damage-segmentation benchmark
from HuggingFace (Voxel51/dacl10k) into data/cv/dacl10k, resumable + threaded.

Why not huggingface_hub.snapshot_download? It fails on this Windows box
("Data processing error ... os error 3"). This walks the HF tree API and
fetches each file with a small thread pool, skipping anything already on disk
with the correct size. Re-run anytime to resume.

  python scripts/download_dacl10k.py [--threads 16] [--out data/cv/dacl10k]

License: dacl10k is CC BY-NC 4.0 — research/benchmark use only, NOT production
training data for a commercial product (see vault/08-Startup/Company-Project.md).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = "Voxel51/dacl10k"
BASE = "https://huggingface.co/api/datasets"
RESOLVE = f"https://huggingface.co/datasets/{REPO}/resolve/main"
HEADERS = {"User-Agent": "Mozilla/5.0 SHM-Bridges"}


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def walk_tree(prefix: str) -> list[dict]:
    """Recursively list every file under a tree API prefix."""
    url = f"{BASE}/{REPO}/tree/main/{prefix}"
    entries = json.loads(_get(url))
    files: list[dict] = []
    for e in entries:
        if e["type"] == "directory":
            files.extend(walk_tree(e["path"]))
        else:
            files.append(e)
    return files


def fetch_one(rel: str, dest_root: Path, size: int) -> bool:
    """Download one file (no-op if present & correct size). Returns True on success."""
    dest = dest_root / rel
    if dest.exists() and dest.stat().st_size == size:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    url = f"{RESOLVE}/{rel}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=HEADERS), timeout=120
        ) as r, open(tmp, "wb") as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        tmp.replace(dest)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  [fetch] FAIL {rel}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--out", default="data/cv/dacl10k")
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    out = Path(args.out)
    print("[walk] listing dacl10k tree ...")
    files = walk_tree("data")
    files = [f for f in files if f["type"] == "file"]
    if args.limit:
        files = files[: args.limit]
    total = sum(f.get("size") or 0 for f in files)
    print(f"[walk] {len(files)} files, {total/1e6:.1f} MB")

    done_ok = 0
    done_fail = 0
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futures = [
            ex.submit(fetch_one, f["path"], out, f.get("size") or 0) for f in files
        ]
        for i, fut in enumerate(as_completed(futures), 1):
            if fut.result():
                done_ok += 1
            else:
                done_fail += 1
            if i % 200 == 0 or i == len(futures):
                print(f"[fetch] {i}/{len(futures)} ok={done_ok} fail={done_fail}")

    print(f"[done] ok={done_ok} fail={done_fail}")
    return 0 if done_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
