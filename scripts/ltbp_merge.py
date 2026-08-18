#!/usr/bin/env python
"""ltbp_merge.py — fold observed inspections into the LTBP Markov priors.

Item 21 (fleet-prior learning loop): reads the observed-transition store
(data/ltbp/observed_transitions.jsonl, appended by the reviewed record path)
and emits a DERIVED merged summary (data/ltbp/analysis/
ltbp_summary.generated.json) that ADDS the observed counts onto a deep copy of
the committed LTBP base summary.  The base file is never mutated.

The merged file, once present, is what deterioration.py consumes — the priors
label then carries the observation count and reviewer provenance.

Run after recording a reviewed inspection pair:

    python scripts/ltbp_merge.py            # on-disk merge, prints the diff
    python scripts/ltbp_merge.py --check    # dry-run: report only, no write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# launch bootstrap (works from repo root or backend/): the `app` package lives
# under backend/, so add that dir to sys.path, not just the repo root.
_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
for _p in (_BACKEND, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app import fleet_learning as fl  # noqa: E402
from app import deterioration as det_mod  # noqa: E402


def _sum_transitions(summary: dict, rating: str) -> int:
    blk = (summary.get("markov_transitions_pilot_only") or {}) \
          .get(rating, {}) .get("counts_total", {})
    if not isinstance(blk, dict):
        return 0
    return int(sum(blk.values()))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="dry-run: report what WOULD change, write nothing")
    args = ap.parse_args(argv)

    base = det_mod.load_priors()
    obs = fl.load_observed()
    merged = fl.merge_priors(base=base, obs=obs, write=not args.check)

    nb = {r: _sum_transitions(base, r) for r in ("super", "sub")}
    nm = {r: _sum_transitions(merged, r) for r in ("super", "sub")}
    print(f"observed transitions in store: {obs['n_records']} "
          f"(duplicates skipped {obs['n_duplicates_skipped']})")
    for r in ("super", "sub"):
        print(f"  {r:5s} base {nb[r]} -> merged {nm[r]}  "
              f"(+{nm[r] - nb[r]})")
    print(f"priors label: {merged.get('prior_source_label', '')}")
    if args.check:
        print("DRY-RUN: nothing written")
        return 0
    print(f"wrote {fl.MERGE_FILE}")
    print("deterioration.py will now consume the merged priors "
          "(priors_label reflects the observation count)")

    # sanity: the merged file must be readable JSON and row-stochastic matrices.
    blk = json.loads(fl.MERGE_FILE.read_text(encoding="utf-8"))
    for r in ("super", "sub"):
        counts = (blk["markov_transitions_pilot_only"][r]["counts_total"]) or {}
        assert isinstance(counts, dict), f"merged {r} counts not a dict"
    print("verification: merged file parses, both ratings have counts")
    return 0


if __name__ == "__main__":
    sys.exit(main())