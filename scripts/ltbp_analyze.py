"""LTBP / InfoBridge analysis — real NBI condition data → deterioration + Markov priors.

Reads the FHWA InfoBridge "Selected Bridges" exports under data/ltbp/:
  - ltbp_pilot_44br.txt  (44 LTBP pilot bridges, 1993-2025 = REAL longitudinal)
  - ltbp_fleet_1892br.txt (1,892-bridge fleet sample = cross-sectional snapshot)

and derives honest priors for the twin's Markov deterioration model (roadmap #8):

  1. Empirical Markov transition matrix — year-over-year super/sub condition-state
     transitions, computed from the PILOT bridges ONLY (the one real longitudinal set).
  2. Cross-sectional deterioration curve — current super/sub condition vs bridge age,
     computed from the FLEET (large N, one condition state per bridge).
  3. Fleet snapshot — current condition / age / climate distribution.

NOTA BENE (data quirk, verified): the field this export names "58 - Deck Condition
Rating" is saturated (0/1, constant within every bridge) — it is NOT the real NBI
0-9 deck rating. We therefore use only super (59) and sub (60), which are genuine
NBI ratings in this export. Deck condition must come from another source.

Outputs (small, committed): data/ltbp/analysis/ltbp_summary.json + ltbp_report.md.
Provenance: FHWA InfoBridge public "Selected Bridges" export, downloaded 2026-08-14.
Raw files are gitignored. License: US federal open data.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ltbp"
OUT = DATA / "analysis"

PILOT = DATA / "ltbp_pilot_44br.txt"
FLEET = DATA / "ltbp_fleet_1892br.txt"

C_YEAR = "Year"
C_SN = "8 - Structure Number"
C_AGE = "Bridge Age (yr)"
C_CAT10 = "CAT10 - Bridge Condition"
C_SUPER = "59 - Superstructure Condition Rating"
C_SUB = "60 - Substructure Condition Rating"
C_FT = "Number of Freeze-Thaw Cycles"
C_TEMP = "Average Temperature"
C_TRAFFIC = "29 - Average Daily Traffic"

# Only super/sub — deck column is a saturated/broken export field (see docstring).
COND_KEYS = {"super": C_SUPER, "sub": C_SUB}


def load(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            # Some export rows carry a trailing empty field beyond the header;
            # csv.DictReader buckets it under a None key as a list. Skip it.
            rows.append({k: (r.get(k) or "").strip() for k in r if k is not None})
    return rows


def _num(v: str) -> float | None:
    v = (v or "").strip().strip("'")
    if v in ("", "N", "n", "NA"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _cond(r: dict, key: str) -> int | None:
    v = _num(r.get(key))
    return int(v) if v is not None and 0 <= v <= 9 else None


def group_by_bridge(rows: list[dict]) -> dict[str, list[dict]]:
    bridges: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        bridges[r.get(C_SN) or "UNKNOWN"].append(r)
    return dict(bridges)


def markov_from_pilot(pilot: list[dict]) -> dict[str, dict]:
    """Year-over-year state transitions from the real longitudinal pilot set."""
    bridges = group_by_bridge(pilot)
    counts: dict[str, np.ndarray] = {k: np.zeros((10, 10), dtype=np.int64)
                                     for k in COND_KEYS}
    n_bridges_seen = {k: 0 for k in COND_KEYS}
    for rows in bridges.values():
        for k, col in COND_KEYS.items():
            series = sorted(
                ((int(y), c) for (y, c) in
                 ((_num(r.get(C_YEAR)), _cond(r, col)) for r in rows)
                 if y is not None and c is not None),
                key=lambda t: t[0],
            )
            # de-duplicate consecutive identical years (shouldn't happen, be safe)
            seen_years = set()
            uniq = []
            for y, c in series:
                if y not in seen_years:
                    seen_years.add(y)
                    uniq.append((y, c))
            moved = 0
            for (y0, c0), (y1, c1) in zip(uniq, uniq[1:]):
                if y1 - y0 != 1:
                    continue  # gap → no direct transition
                counts[k][c0, c1] += 1
                if c1 != c0:
                    moved += 1
            n_bridges_seen[k] += (1 if moved else 0)
    out = {}
    for k, M in counts.items():
        # Deterioration-only prior: keep stay-same + worsen (j <= i); drop
        # improvements (rehab / misread) so the prior is conditional on no rehab.
        det = np.tril(M, 0).copy()
        row_sums = det.sum(axis=1)
        P = np.divide(det, row_sums[:, None],
                      out=np.zeros_like(det, dtype=float),
                      where=row_sums[:, None] > 0)
        out[k] = {
            "bridges_with_change": int(n_bridges_seen[k]),
            "counts_total": {f"{i}->{j}": int(M[i, j])
                             for i in range(10) for j in range(10) if M[i, j] > 0},
            "prob_deterioration_only": {
                str(i): {
                    "n": int(row_sums[i]),
                    "stay_same": round(float(P[i, i]), 4),
                    "degrade_1": round(float(P[i, i - 1]), 4) if i > 0 else 0.0,
                }
                for i in range(10) if row_sums[i] > 0
            },
        }
    return out


def cross_section(fleet: list[dict]) -> dict[str, list[dict]]:
    """Current condition vs bridge age across the fleet (cross-sectional)."""
    out: dict[str, list[dict]] = {k: [] for k in COND_KEYS}
    for rows in group_by_bridge(fleet).values():
        last = rows[-1]  # any row is the snapshot; take last
        age = _num(last.get(C_AGE))
        if age is None:
            continue
        age_int = int(age)
        if not (0 <= age_int <= 120):
            continue
        for k, col in COND_KEYS.items():
            c = _cond(last, col)
            if c is not None:
                out[k].append((age_int, c))
    curve: dict[str, list[dict]] = {}
    for k, pairs in out.items():
        buckets: dict[int, list[int]] = defaultdict(list)
        for a, c in pairs:
            buckets[a].append(c)
        curve[k] = [
            {"age": a, "n": len(buckets[a]),
             "mean_cond": round(float(np.mean(buckets[a])), 3),
             "p25": round(float(np.percentile(buckets[a], 25)), 2),
             "p75": round(float(np.percentile(buckets[a], 75)), 2)}
            for a in sorted(buckets)
        ]
    return curve


def fleet_snapshot(fleet: list[dict]) -> dict:
    snap = defaultdict(list)
    cat10 = Counter()
    cat10_misaligned = 0
    for rows in group_by_bridge(fleet).values():
        last = rows[-1]
        cat = last.get(C_CAT10, "").strip().strip("'")
        if cat in ("Good", "Fair", "Poor"):
            cat10[cat] += 1
        elif cat:
            cat10_misaligned += 1  # export misalignment leaks facility names here
        age = _num(last.get(C_AGE))
        if age is not None:
            snap["age"].append(age)
        ft = _num(last.get(C_FT))
        if ft is not None:
            snap["ft"].append(ft)
        temp = _num(last.get(C_TEMP))
        if temp is not None:
            snap["temp"].append(temp)
        tr = _num(last.get(C_TRAFFIC))
        if tr is not None:
            snap["ad"].append(tr)
        for k, col in COND_KEYS.items():
            c = _cond(last, col)
            if c is not None:
                snap[k].append(c)

    def m(x):
        return round(float(np.mean(x)), 2) if x else None

    return {
        "cat10_current": dict(cat10.most_common()),
        "cat10_misaligned_rows": cat10_misaligned,
        "mean_age": m(snap["age"]),
        "mean_ft_cycles": m(snap["ft"]),
        "mean_temp_c": m(snap["temp"]),
        "mean_adt": m(snap["ad"]),
        "mean_super": m(snap["super"]),
        "mean_sub": m(snap["sub"]),
        "n_bridges": len(group_by_bridge(fleet)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pilot = load(PILOT)
    fleet = load(FLEET)

    print(f"pilot records: {len(pilot):,}  fleet records: {len(fleet):,}")

    markov = markov_from_pilot(pilot)
    curve = cross_section(fleet)
    snap = fleet_snapshot(fleet)

    summary = {
        "provenance": "FHWA InfoBridge Selected-Bridges exports, 2026-08-14 (public, federal open data)",
        "pilot_bridges": len(group_by_bridge(pilot)),
        "fleet_bridges": snap["n_bridges"],
        "note_deck_column": "This export's '58 - Deck Condition Rating' is a saturated 0/1 field "
                            "(constant within every bridge) — NOT the real NBI deck rating. "
                            "Analysis uses super (59) and sub (60) only.",
        "fleet_snapshot": snap,
        "markov_transitions_pilot_only": markov,
        "cross_sectional_condition_vs_age_fleet": curve,
        "honesty_labels": {
            "markov": "Empirical transitions from 44 LTBP pilot bridges (real longitudinal "
                      "1993-2025). Small sample; prefer literature priors (Pontis/Cesare) "
                      "when combined, and label accordingly.",
            "curve": "Cross-sectional fleet curve (different bridges at different ages), NOT "
                     "one bridge aging. Good for priors; do not present as longitudinal RUL.",
        },
    }
    with open(OUT / "ltbp_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    # ---- Markdown report ----
    L = [
        "# LTBP / InfoBridge — empirical deterioration + Markov priors",
        "",
        f"_44 LTBP pilot bridges (real longitudinal 1993-2025) + {snap['n_bridges']} bridge fleet "
        "cross-section, from FHWA InfoBridge Selected-Bridges exports (2026-08-14). Regenerate: "
        "`python scripts/ltbp_analyze.py`._",
        "",
        "> ⚠️ **Data quirk:** this export's `58 - Deck Condition Rating` is a saturated 0/1 field "
        "(constant within every bridge) — **not** the real NBI deck rating. We use **super (59)** "
        "and **sub (60)** only.",
        "",
        "## Fleet snapshot (cross-sectional)",
        "",
        f"- Bridges: **{snap['n_bridges']}** · mean age **{snap['mean_age']} yr** "
        f"· freeze-thaw **{snap['mean_ft_cycles']}/yr** · mean temp **{snap['mean_temp_c']} °C**",
        f"- Mean superstructure: **{snap['mean_super']}** · substructure: **{snap['mean_sub']}** (NBI 0-9)",
        f"- Mean ADT: **{snap['mean_adt']:,}**",
        "",
        "### CAT10 current condition",
        "",
        "| Condition | # bridges |",
        "|---|---|",
    ]
    for k, v in snap["cat10_current"].items():
        L.append(f"| {k} | {v} |")

    L += ["", "## Cross-sectional condition vs age (fleet, NBI 0-9)", "",
          "Different bridges at different ages — a fleet prior, NOT longitudinal RUL. | age | n | super | sub |",
          "", "| Age | n | super (mean) | sub (mean) |", "|---|---|---|---|"]
    n_buckets = len(curve["super"])
    for i, row in enumerate(curve["super"]):
        sub = curve["sub"][i] if i < len(curve["sub"]) else row
        L.append(f"| {row['age']} | {row['n']} | {row['mean_cond']} | {sub['mean_cond']} |")

    for k in COND_KEYS:
        mk = markov[k]
        L += ["", f"## Markov transition probabilities — {k}, deterioration-only (pilot 44 bridges)",
              "", f"Row = current state; columns = stay-same / degrade-1. "
              f"{mk['bridges_with_change']} pilot bridges showed at least one change. "
              "Small-sample empirical prior — label as such alongside literature values.", "",
              "| from | n | stay same | degrade 1 |", "|---|---|---|---|"]
        for i in range(10):
            p = mk["prob_deterioration_only"].get(str(i))
            if p:
                L.append(f"| {i} | {p['n']} | {p['stay_same']:.3f} | {p['degrade_1']:.3f} |")

    L += ["", "_Source: FHWA InfoBridge / Long-Term Bridge Performance (LTBP). US federal open data._"]
    (OUT / "ltbp_report.md").write_text("\n".join(L), encoding="utf-8")
    print("Wrote", OUT / "ltbp_summary.json", "and", OUT / "ltbp_report.md")


if __name__ == "__main__":
    main()
