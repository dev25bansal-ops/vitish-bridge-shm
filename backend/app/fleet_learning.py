"""
fleet_learning.py — fleet-prior learning loop (§7.6 item 21).

The Markov deterioration priors in ``deterioration.py`` are built from the
STATIC LTBP summary (44 FHWA InfoBridge pilot bridges, 1993-2025).  This module
is the "learning loop" infrastructure that lets REAL, human-reviewed inspection
observations fold into those priors over time, so the priors become the fleet's
own data — the data flywheel the company brief claims (vault/08-Startup/
Company-Project.md moat).

It has to exist BEFORE the first pilot produces data, so that first inspection
pair is captured rather than lost.

    * observed-transitions store — an append-only JSONL log
      (``data/ltbp/observed_transitions.jsonl``, committed empty) of
      (bridge_id, rating, year_t0, condition_t0, condition_t1) records.  The
      record is the one, keyed, deduplicated observation; re-recording the same
      pair returns ``status: "duplicate"`` and is never double-counted.
    * append/merge path — ``merge_priors()`` adds the observed counts onto a
      DEEP COPY of the LTBP base summary's transition counts and emits a
      DERIVED file (``data/ltbp/analysis/ltbp_summary.generated.json``).  The
      committed base file is never mutated; the merged label states exactly what
      was added (fleet prior + N observed inspections).

HONESTY BOUNDARY (Rule 1 / Rule 3 in docs/HONESTY-METHODOLOGY.md): the ingest
source is ONLY a human-reviewed inspection record (two NBI ratings at two
dates, with a named ``recorded_by``).  There is deliberately NO telemetry
auto-ingest — ``condition_from_bhi`` (deterioration.py) is a model assumption,
and recording it as an "observation" would falsify provenance.  A blank
``recorded_by`` is rejected (cannot be attributed to a reviewer).

Determinism: tests hand in a temp store via ``set_store_path`` and call the
pure ``merge_priors(base=..., obs=...)`` overload so unit tests never touch the
committed store.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import deterioration as det_mod
from app.config import PROJECT_ROOT

log = logging.getLogger(__name__)

STORE_ROOT = PROJECT_ROOT / "data" / "ltbp"
OBS_FILE = STORE_ROOT / "observed_transitions.jsonl"
MERGE_FILE = STORE_ROOT / "analysis" / "ltbp_summary.generated.json"

_RATINGS = ("super", "sub")
# NBI 0-9 condition scale (same as the deterioration transition matrix).
_COND_MIN, _COND_MAX = 0, 9

_BASE_PRIORS_BLURB = (
    "empirical LTBP fleet prior, small n (44 FHWA InfoBridge pilot bridges, 1993-2025)")


def _now_ms() -> float:
    return time.time() * 1000.0


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------
_store_path: Path = OBS_FILE
_store_lock = threading.RLock()


def set_store_path(path) -> None:
    """Test hook: point the store at a temp location (module-wide)."""
    global _store_path
    _store_path = Path(path)


def store_path() -> Path:
    return _store_path


def _record_key(rec: dict) -> str:
    """The one key that makes an observation idempotent.

    A bridge, on a rating, inspected in year_t0 at condition_t0 and next at
    condition_t1: that pair is a single observed transition.  Recording the
    same pair twice is a duplicate; a NEW bridge or a different year is not.
    """
    return "|".join((
        str(rec.get("bridge_id", "")),
        str(rec.get("rating", "")),
        str(int(rec.get("year_t0", -1))),
        str(int(rec.get("condition_t0", -1))),
        str(int(rec.get("condition_t1", -1))),
    ))


def validate_observation(rec: dict, existing_keys: set) -> Optional[str]:
    """Return a rejection reason string, or None when the record is valid."""
    bid = rec.get("bridge_id", "")
    if not isinstance(bid, str) or not bid.strip():
        return "bridge_id must be a non-empty string"
    rating = rec.get("rating", "")
    if rating not in _RATINGS:
        return f"rating must be one of {_RATINGS}, got {rating!r}"
    for f in ("condition_t0", "condition_t1"):
        try:
            v = int(rec.get(f, -1))
        except (TypeError, ValueError):
            return f"{f} must be an integer"
        if not (_COND_MIN <= v <= _COND_MAX):
            return f"{f} must be in {_COND_MIN}..{_COND_MAX}, got {v}"
    try:
        year_t0 = int(rec.get("year_t0", -1))
    except (TypeError, ValueError):
        year_t0 = -1
    if year_t0 < 1900 or year_t0 > 2100:
        return f"year_t0 must be a plausible inspection year, got {rec.get('year_t0')!r}"
    rec = dict(rec)
    rec["year_t0"] = year_t0
    rec["condition_t0"] = int(rec["condition_t0"])
    rec["condition_t1"] = int(rec["condition_t1"])
    recorded_by = rec.get("recorded_by")
    if recorded_by is not None and not isinstance(recorded_by, str):
        return "recorded_by must be a string naming the human reviewer"
    if "recorded_by" in rec and not (recorded_by or "").strip():
        return ("recorded_by cannot be blank — omit the field to mark the "
                "observation UNREVIEWED, or name the reviewer")
    key = _record_key(rec)
    if key in existing_keys:
        return f"duplicate observation already recorded: {key}"
    return None


def record_observation(rec: dict) -> dict:
    """Validate and append one observed transition to the store.

    Returns ``{"status": "recorded"|"duplicate"|"invalid", "record": {...}}``.
    Idempotent: an identical (bridge, rating, year, from, to) pair is rejected
    and never double-counted.  The only caller is the offline review path —
    ``scripts/record_observation``/manual calls, never telemetry.
    """
    with _store_lock:
        existing = {_record_key(r) for r in _iter_records()}
        reason = validate_observation(rec, existing)
        if reason:
            if reason.startswith("duplicate"):
                return {"status": "duplicate", "reason": reason,
                        "record": {k: rec.get(k) for k in
                                   ("bridge_id", "rating", "year_t0",
                                    "condition_t0", "condition_t1")}}
            return {"status": "invalid", "reason": reason, "record": rec}

        rec = dict(rec)
        rec["year_t0"] = int(rec["year_t0"])
        rec["condition_t0"] = int(rec["condition_t0"])
        rec["condition_t1"] = int(rec["condition_t1"])
        rec.setdefault("source", "inspection")
        rec.setdefault("recorded_by", "UNREVIEWED")
        rec.setdefault("inspected_at_ms", _now_ms())
        rec.setdefault("recorded_ms", _now_ms())

        path = store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "observed_transition",
                                "data": rec}) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        log.info("observed transition recorded: %s %s %s->%s (%s)",
                 rec["bridge_id"], rec["rating"], rec["condition_t0"],
                 rec["condition_t1"], rec["recorded_by"])
        return {"status": "recorded", "record": rec}


def _iter_records(path: Optional[Path] = None) -> List[dict]:
    path = path or store_path()
    out: List[dict] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("kind") == "observed_transition" and isinstance(obj.get("data"), dict):
            out.append(obj["data"])
    return out


def load_observed() -> dict:
    """Dedupe the store into per-rating transition counts + provenance stats."""
    records = _iter_records()
    counts: Dict[str, Dict[str, int]] = {"super": {}, "sub": {}}
    bridges: Dict[str, set] = {"super": set(), "sub": set()}
    seen: set = set()
    skipped = 0
    first_ts = last_ts = None
    for r in records:
        try:
            rating = r.get("rating", "")
            key = _record_key(r)
        except Exception:
            skipped += 1
            continue
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        if rating not in counts:
            continue
        t0, t1 = int(r.get("condition_t0", -1)), int(r.get("condition_t1", -1))
        counts[rating][f"{t0}->{t1}"] = counts[rating].get(f"{t0}->{t1}", 0) + 1
        bridges[rating].add(str(r.get("bridge_id", "")))
        ts = r.get("recorded_ms")
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            ts = None
        if ts is not None:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)
    total = sum(sum(c.values()) for c in counts.values())
    return {
        "counts_total": counts,
        "n_records": len(seen),
        "n_duplicates_skipped": skipped,
        "n_bridges": {r: sorted(bridges[r]) for r in _RATINGS},
        "n_bridge_ids": sum(len(bridges[r]) for r in _RATINGS),
        "first_recorded_ms": first_ts,
        "last_recorded_ms": last_ts,
        "total_transitions": total,
        "store_path": str(store_path()),
    }


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------
def _merge_counts(base_counts: dict, observed_counts: dict) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for k, v in (base_counts or {}).items():
        out[str(k)] = int(v)
    for k, v in (observed_counts or {}).items():
        out[str(k)] = out.get(str(k), 0) + int(v)
    return out


def merge_priors(base: Optional[dict] = None, obs: Optional[dict] = None,
                 write: bool = True) -> dict:
    """Fold observed transitions onto the LTBP base priors (append path).

    Pure path: ``merge_priors(base=..., obs=...)`` merges in-memory and returns
    the merged summary without touching disk.  On-disk path (both args None):
    reads ``deterioration.load_priors()`` + the local store and writes
    ``ltbp_summary.generated.json``.

    The committed ``ltbp_summary.json`` is NEVER mutated — the merged output is
    a separate derived file, and its label states exactly what was added.
    """
    if base is None:
        base = det_mod.load_priors()
    if obs is None:
        obs = load_observed()

    merged = json.loads(json.dumps(base))  # deep copy
    for rating in _RATINGS:
        base_block = (merged.get("markov_transitions_pilot_only") or {}) \
            .get(rating) or {}
        base_counts = base_block.get("counts_total") or {}
        if not isinstance(base_counts, dict):
            base_counts = {}
        obs_counts = (obs.get("counts_total") or {}).get(rating) or {}
        if not isinstance(obs_counts, dict):
            obs_counts = {}
        merged_counts = _merge_counts(base_counts, obs_counts)
        blk = merged.setdefault("markov_transitions_pilot_only", {}) \
                    .setdefault(rating, {})
        blk["counts_total"] = merged_counts
        blk.setdefault("bridges_with_change",
                       base_block.get("bridges_with_change", 0))

    n_records = int(obs.get("n_records", 0))
    if "n_records" not in obs:  # pure path with counts only -> derive
        n_records = sum(
            sum(v) if isinstance(v, dict) else 0
            for v in (obs.get("counts_total") or {}).values()
        )
    merged["observed_transitions"] = {
        "counts_total": (obs.get("counts_total") or {}),
        "n_records": n_records,
        "n_duplicates_skipped": int(obs.get("n_duplicates_skipped", 0)),
        "n_bridges": (obs.get("n_bridge_ids", 0)),
        "note": ("observed human-reviewed inspection transitions appended to "
                 "the LTBP fleet prior; each record names its reviewer "
                 "(recorded_by) — never telemetry-derived."),
    }
    merged["prior_source_label"] = _merged_label(n_records)

    if write:
        out = MERGE_FILE
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, out)
        log.info("merged priors written to %s (%d observed records folded)",
                 out, n_records)
    return merged


def _merged_label(n_records: int) -> str:
    if n_records <= 0:
        return (_BASE_PRIORS_BLURB + " (no observed transitions merged yet)")
    return (f"{_BASE_PRIORS_BLURB} + {n_records} observed inspections "
            f"(human-reviewed — see recorded_by on each observation)")


def merged_present() -> bool:
    return MERGE_FILE.exists()


def merge_status() -> dict:
    """Read-only summary of which prior file is in use + observation stats."""
    used = "merged" if merged_present() else "base"
    obs = load_observed()
    label = merged_label() if used == "merged" else _merged_label(int(obs.get("n_records", 0)))
    return {
        "prior_file": used,
        "base_file": str(det_mod._SUMMARY),
        "merged_file": str(MERGE_FILE),
        "observed_count": int(obs.get("n_records", 0)),
        "observed_total_transitions": int(obs.get("total_transitions", 0)),
        "duplicates_skipped": int(obs.get("n_duplicates_skipped", 0)),
        "last_recorded_at_ms": obs.get("last_recorded_ms"),
        "priors_label": label,
        "note": ("Read-only status.  Folding observations into the priors is a "
                 "reviewed offline action (scripts/ltbp_merge.py) — nothing "
                 "auto-ingests telemetry."),
    }


def merged_label() -> str:
    """The current priors label: merged-file label when present, else base."""
    if MERGE_FILE.exists():
        try:
            blk = json.loads(MERGE_FILE.read_text(encoding="utf-8"))
            lbl = blk.get("prior_source_label")
            if isinstance(lbl, str) and lbl.strip():
                return lbl
        except Exception:
            pass
    return _BASE_PRIORS_BLURB