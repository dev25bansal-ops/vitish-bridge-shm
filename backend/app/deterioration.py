"""
D1-4 · Markov deterioration with empirical LTBP priors.

Loads the real FHWA InfoBridge longitudinal transitions
(``data/ltbp/analysis/ltbp_summary.json`` — 44 LTBP pilot bridges observed
1993–2025) and exposes an honest year-over-year Markov projection:

    condition_{t+1} ~ Multinomial( transition_matrix[rating][condition_t] )

The transition matrices are built from the **empirical transition counts**
(both deterioration *and* repair appear in the real longitudinal data), so the
projection reflects what actually happened to those bridges — not a hand-picked
decay curve.

Honesty notes:
  * This is a fleet prior + Markov projection.  It is NEVER a certified RUL or
    a Paris-law forecast.  Every API/UI consumer must keep the label
    ``"empirical LTBP prior, small n"``.
  * ``condition_from_bhi`` is a MODEL ASSUMPTION mapping the live BHI (0–100)
    onto the NBI 0–9 rating scale so the same engine can project the hero
    bridge; it is not an NBI inspection and is labelled as such in the payload.
  * Small-n states: where fewer than ~5 observed transitions exist, the row
    defaults to "stay" (identity) and the provenance marks it ``empirical: false``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from app.config import PROJECT_ROOT

log = logging.getLogger(__name__)

# --- priors data ---------------------------------------------------------------
_SUMMARY = PROJECT_ROOT / "data" / "ltbp" / "analysis" / "ltbp_summary.json"

PRIORS_LABEL = "empirical LTBP prior, small n (44 FHWA InfoBridge pilot bridges, 1993-2025)"
_RATINGS = ("super", "sub")

_priors_cache: Optional[dict] = None


def load_priors() -> dict:
    """Lazy-load the LTBP summary (real FHWA InfoBridge longitudinal counts)."""
    global _priors_cache
    if _priors_cache is None:
        if not _SUMMARY.exists():
            raise FileNotFoundError(
                f"LTBP summary missing: {_SUMMARY} — run scripts/ltbp_analyze.py")
        _priors_cache = json.loads(_SUMMARY.read_text(encoding="utf-8"))
    return _priors_cache


# --- transition matrices --------------------------------------------------------
def transition_matrix(rating: str) -> tuple:
    """(10x10 row-stochastic transition matrix, provenance dict) for an NBI
    rating (``super`` | ``sub``), built from the empirical transition counts.

    Rows with < MIN_N observed transitions fall back to the identity row and are
    flagged ``empirical: false`` (honest small-n handling).
    """
    if rating not in _RATINGS:
        raise ValueError(f"rating must be one of {_RATINGS}, got {rating!r}")
    data = load_priors()["markov_transitions_pilot_only"][rating]
    counts = data["counts_total"]

    P = np.zeros((10, 10))
    empirical_rows = set()
    for key, c in counts.items():
        try:
            i, j = (int(v) for v in key.split("->"))
        except ValueError:
            continue
        P[i, j] += c
    for i in range(10):
        total = float(P[i].sum())
        if total < 5.0:  # small-n row -> identity ("stay"), flagged below
            P[i] = 0.0
            P[i, i] = 1.0
        else:
            P[i] /= total
            empirical_rows.add(i)

    missing = sorted(set(range(10)) - empirical_rows)
    return P, {
        "rating": rating,
        "n_bridges": data["bridges_with_change"],
        "empirical_rows": sorted(empirical_rows),
        "small_n_defaulted_rows": missing,
        "note": ("rows with fewer than 5 observed transitions default to 'stay' "
                 "instead of pretending to know the rate"),
    }


# --- BHI -> NBI condition mapping (MODEL ASSUMPTION) ----------------------------
def condition_from_bhi(bhi: float) -> int:
    """Map the live BHI (0-100) onto the NBI 0-9 condition scale.

    MODEL ASSUMPTION, not an NBI inspection:  NBI ≈ 1 + 8·(BHI/100), so
    BHI 87 → NBI 8 (good), BHI 67 → 6 (fair), BHI 34 → 4 (poor).  Kept in one
    place so the mapping is easy to audit and never silently changes.
    """
    if bhi is None or np.isnan(bhi):
        return 8
    nbi = 1.0 + 8.0 * max(0.0, min(100.0, float(bhi))) / 100.0
    return int(round(nbi))


# --- projection ------------------------------------------------------------------
def _percentiles(dist: np.ndarray, qs=(0.10, 0.90)) -> list:
    cdf = np.cumsum(dist)
    out = []
    for q in qs:
        idx = int(np.searchsorted(cdf, q))
        out.append(int(min(9, max(0, idx))))
    return out


def project(rating: str, current: int, years: int = 30,
            threshold: int = 4) -> List[dict]:
    """Year-over-year Markov projection of an NBI condition.

    Returns one row per year (years 1..N):
      year, expected (mean NBI), p10/p90 (fan), p_poor (P(NBI <= threshold)),
      dist (full 10-vector probability over NBI 0..9).
    """
    P, prov = transition_matrix(rating)
    dist = np.zeros(10)
    dist[int(np.clip(current, 0, 9))] = 1.0
    rows = []
    for y in range(1, years + 1):
        dist = dist @ P
        expected = float(np.dot(np.arange(10), dist))
        p10, p90 = _percentiles(dist)
        rows.append({
            "year": y,
            "expected": round(expected, 2),
            "p10": p10,
            "p90": p90,
            "p_poor": round(float(dist[: threshold + 1].sum()), 4),
            "dist": [round(float(v), 4) for v in dist.tolist()],
        })
    return rows


def next_inspection(rating: str, current: int, threshold: int = 4,
                    p_cross: float = 0.25, max_years: int = 100) -> Optional[int]:
    """First year the projected P(NBI <= threshold) reaches ``p_cross`` — the
    honest "next inspection trigger" (probabilistic, not a deterministic RUL)."""
    rows = project(rating, current, years=max_years, threshold=threshold)
    for r in rows:
        if r["p_poor"] >= p_cross:
            return r["year"]
    return None


def bridge_deterioration(bridge_id: str, bhi: float, years: int = 30,
                         rating: str = "super") -> dict:
    """One self-describing deterioration payload for the API (used by D2-11)."""
    if rating not in _RATINGS:
        raise ValueError(f"rating must be one of {_RATINGS}, got {rating!r}")
    current = condition_from_bhi(bhi)
    rows = project(rating, current, years=years)
    nxt = next_inspection(rating, current)
    _, prov = transition_matrix(rating)
    return {
        "bridge": bridge_id,
        "rating": rating,
        "current_bhi": round(float(bhi), 1),
        "current_condition": current,
        "priors_label": PRIORS_LABEL,
        "transition_provenance": prov,
        "years": years,
        "projection": rows,
        "next_inspection_year": nxt,
        "next_inspection_rule": f"first year P(NBI <= {4}) >= {0.25:.0%}",
        "note": ("Markov projection under an empirical LTBP fleet prior — a "
                 "probabilistic model, not a certified RUL and no Paris-law "
                 "forecast. condition_from_bhi is a model assumption, not an "
                 "NBI inspection."),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(bridge_deterioration("reg-01", 74.0, years=25), indent=1)[:4000])
