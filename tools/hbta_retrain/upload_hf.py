"""tools/hbta_retrain/upload_hf.py — push the HBTA retrain tar to Hugging Face.

Why this exists: the `hf`/`huggingface-cli` entry points are broken in this
Python 3.14 env (click's Context.lookup_default() signature clash), but the
`huggingface_hub` library API works fine. This uses the API directly.

Writes a README card with attribution + sha256 (HBTA is CC-BY-4.0, so
redistribution is allowed WITH attribution), then uploads the tar.

Usage (PowerShell):
  $env:HF_TOKEN = "hf_..."                      # a WRITE-scoped token from
                                                # https://huggingface.co/settings/tokens
  python tools/hbta_retrain/upload_hf.py YOUR_USERNAME/hbta-retrain

The repo is created if it does not exist (model type). Re-run to overwrite —
uploads are idempotent. The token is read from the environment only and never
written to disk.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi

TAR = Path(__file__).resolve().parents[2] / "hbta_retrain_2026-08-15.tar.gz"
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
- `sha256` of `hbta_retrain_2026-08-15.tar.gz`: {sha}
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Upload the HBTA retrain tar to HF")
    ap.add_argument("repo", help="e.g. YOUR_USERNAME/hbta-retrain")
    ap.add_argument("--tar", type=Path, default=TAR, help="tar to upload")
    ap.add_argument("--private", action="store_true",
                    help="create the repo private (default: public — flip a "
                         "public repo to private later does NOT un-expose it)")
    ap.add_argument("--card-repo-id", type=str, default=None,
                    help="repo to receive the README card (default: same as repo)")
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

    sha = sha256_of(args.tar)
    api = HfApi(token=token)
    print(f"  [hf] ensure repo {args.repo} exists (model, "
          f"{'private' if args.private else 'public'})")
    api.create_repo(repo_id=args.repo, repo_type="model", exist_ok=True,
                    private=args.private)
    print(f"  [hf] upload README card (sha256 {sha})")
    api.upload_file(
        path_or_fileobj=CARD.format(sha=sha).encode("utf-8"),
        path_in_repo="README.md",
        repo_id=args.repo,
        repo_type="model",
    )
    print(f"  [hf] upload {args.tar.name} ({args.tar.stat().st_size/1e9:.2f} GB) "
          f"— single request (multipart resume is >5GB-only); if the network "
          f"drops, just re-run: the upload is idempotent (overwrites)")
    url = api.upload_file(
        path_or_fileobj=str(args.tar),
        path_in_repo=args.tar.name,
        repo_id=args.repo,
        repo_type="model",
    )
    print(f"  [hf] done: {url}")
    print(f"  download URL (public repo, no token needed on the server):\n"
          f"  https://huggingface.co/{args.repo}/resolve/main/{args.tar.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
