"""tools/hbta_retrain/upload_hf_parts.py — split the HBTA tar and upload parts in parallel.

Why parts: a single 2.4 GB file uploads over ONE LFS connection (multipart
resume is >5GB-only) — measured ~90 kB/s, i.e. ~6-7 h — and a single giant PUT
also crashed this Windows box (SIGSEGV) twice. Splitting into ~480 MB parts and
uploading them with create_commit(num_threads=5) runs five connections in
parallel (total rate = sum of per-part rates) and keeps each request small.

gzip is stream-safe, so the server reassembles by concatenation:
  curl -o p01 ...p01  ; ... ; cat p01 p02 p03 p04 p05 > hbta_retrain_2026-08-15.tar.gz
and sha256-verifies against the printed digest.

The repo is created private (exist_ok). Re-run is idempotent — parts overwrite.
Token is read from the environment only, never written to disk.

Usage (PowerShell):
  $env:HF_TOKEN = "hf_..."        # write-scoped token
  python tools/hbta_retrain/upload_hf_parts.py YOUR_USERNAME/hbta-retrain
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from huggingface_hub import CommitOperationAdd, HfApi

TAR = Path(__file__).resolve().parents[2] / "hbta_retrain_2026-08-15.tar.gz"
PARTS_DIR = Path(__file__).resolve().parents[2] / ".verify" / "hf_parts"
CARD = """---
license: cc-by-4.0
---

# HBTA per-structure retrain package (VITISH-2026 bridge SHM)

Retraining bundle for the Hell Bridge Test Arena (HBTA) full-scale steel truss
bridge — the repo's vibration pipeline (VAE/OCSVM + LSTM-AE, envelope-floor+push)
retrained per structure type, per PostHackathon §117. See the bundled
`README.md` (inside the tar) for the two-lane (ACCEL/STRAIN) instructions and
the honest measured findings.

- `data_100Hz.h5` is HBTA (Hell Bridge Test Arena), **CC-BY-4.0** — attribution
  to the HBTA dataset authors. Full dataset: see the HBTA data release.
- `hbta_retrain_2026-08-15.tar.gz` (2.40 GB) is stored SPLIT into parts
  `hbta_retrain_2026-08-15.tar.gz.part01..05` for parallel upload. Reassemble:
  `cat hbta_retrain_2026-08-15.tar.gz.part0* > hbta_retrain_2026-08-15.tar.gz`
- `sha256` of the reassembled tar: {sha}
- Contents: `data_100Hz.h5` + `prep_hbta.py` + `run_retrain.sh` +
  `verify_hbta.py` (score-level + feature-level + RMS reference monitor) +
  `models/vibration/` + `README.md` + `requirements.txt`.
"""


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def split_tar(tar: Path, part_size_mb: int, outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    part_size = part_size_mb * 1024 * 1024
    paths: list[Path] = []
    with open(tar, "rb") as f:
        i = 0
        while True:
            chunk = f.read(part_size)
            if not chunk:
                break
            p = outdir / f"{tar.name}.part{i + 1:02d}"
            p.write_bytes(chunk)
            paths.append(p)
            i += 1
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Split + parallel-upload HBTA tar to HF")
    ap.add_argument("repo", help="e.g. YOUR_USERNAME/hbta-retrain")
    ap.add_argument("--tar", type=Path, default=TAR, help="tar to split+upload")
    ap.add_argument("--part-size-mb", type=int, default=480)
    ap.add_argument("--threads", type=int, default=5)
    ap.add_argument("--keep-parts", action="store_true",
                    help="keep part files in .verify/hf_parts (default: delete after upload)")
    args = ap.parse_args(argv)

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN is not set. Run in PowerShell:\n"
              "  $env:HF_TOKEN = \"hf_...\"   # write-scoped token from "
              "https://huggingface.co/settings/tokens", file=sys.stderr)
        return 1
    if not args.tar.exists():
        print(f"ERROR: tar not found: {args.tar}", file=sys.stderr)
        return 1

    print(f"  [split] {args.tar.name} ({args.tar.stat().st_size/1e9:.2f} GB) "
          f"-> parts of {args.part_size_mb} MB")
    parts = split_tar(args.tar, args.part_size_mb, PARTS_DIR)
    for p in parts:
        print(f"    {p.name}: {p.stat().st_size/1e6:.1f} MB")

    sha = sha256_of(args.tar)
    api = HfApi(token=token)
    print(f"  [hf] ensure repo {args.repo} exists (model, PRIVATE)")
    api.create_repo(repo_id=args.repo, repo_type="model", exist_ok=True, private=True)
    print(f"  [hf] upload README card (sha256 {sha})")
    api.upload_file(
        path_or_fileobj=CARD.format(sha=sha).encode("utf-8"),
        path_in_repo="README.md",
        repo_id=args.repo,
        repo_type="model",
    )

    ops = [CommitOperationAdd(path_in_repo=p.name, path_or_fileobj=str(p))
           for p in parts]
    print(f"  [hf] upload {len(parts)} parts in parallel ({args.threads} threads) — "
          f"idempotent, re-run on drop")
    api.create_commit(
        repo_id=args.repo,
        repo_type="model",
        operations=ops,
        commit_message=f"HBTA retrain tar split into {len(parts)} parts (sha256 {sha[:12]})",
        num_threads=args.threads,
    )

    # Verify each part landed: HEAD the resolve URL, compare Content-Length.
    import requests
    ok = True
    for p in parts:
        url = (f"https://huggingface.co/{args.repo}/resolve/main/{p.name}")
        r = requests.head(url, headers={"Authorization": f"Bearer {token}"}, allow_redirects=True)
        got = int(r.headers.get("Content-Length", -1))
        want = p.stat().st_size
        status = "OK" if r.status_code == 200 and got == want else f"MISMATCH (HTTP {r.status_code}, len {got})"
        if status != "OK":
            ok = False
        print(f"  [verify] {p.name}: {status}")
    if not ok:
        print("ERROR: one or more parts did not verify; re-run to overwrite.", file=sys.stderr)
        return 2

    print(f"  [done] all parts uploaded + verified. sha256 of reassembled tar: {sha}")
    print("  download (private repo, needs token on the server):")
    for p in parts:
        print(f"    wget --header=\"Authorization: Bearer $HF_TOKEN\" "
              f"-O {p.name} https://huggingface.co/{args.repo}/resolve/main/{p.name}")
    print("  reassemble + check:")
    print("    cat hbta_retrain_2026-08-15.tar.gz.part0* > hbta_retrain_2026-08-15.tar.gz")
    print(f"    sha256sum hbta_retrain_2026-08-15.tar.gz   # expect {sha}")
    if not args.keep_parts:
        for p in parts:
            p.unlink(missing_ok=True)
        print(f"  [cleanup] removed local parts ({PARTS_DIR})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
