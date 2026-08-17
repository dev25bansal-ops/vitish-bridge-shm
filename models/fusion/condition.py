"""
D1-3 · condition card from the crack index (never a raw CV score).

Segmentation detections -> crack index -> relative severity -> condition state
(NBI band + post-Morandi-style risk class) WITH confidence.  The mapping
thresholds below are documented and auditable; the card always carries the
honesty label that it is a *relative severity reading*, not a certified
structural assessment.

Two honest sources feed the card:
  * ``source="segmentation"`` — real detections from models/cv/inference.py
    (YOLO-seg preferred, OpenCV heuristic fallback).
  * ``source="live-cv-subindex"`` — the live fused ``cv`` sub-index mapped onto
    the SAME calibrated scale, so the card works offline/without a camera but
    is always labeled as the live sub-index, not an image measurement.

Mapping (documented in this file — every threshold is auditable):
  crack burden   B    = sum over dets of conf * severity        (per frame)
  crack index    ci   = 1 - exp(-B / B_REF),   B_REF = 0.5      (saturating)
  severity       light/moderate/severe/critical  at ci 0.15/0.35/0.60
  NBI condition  = 9 - 9*ci  rounded to 0..9   (standard NBI bands below;
                    band 0 'Failed' is reachable only at ci == 1.0)
  risk class     A/B/C/D    at ci 0.15/0.35/0.60 (post-Morandi style)
  confidence     0.4..0.95  grows with detector mode + evidence count
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from models.cv.crack_width import aggregate_width  # item 18: px width evidence

# --- documented mapping constants -----------------------------------------------
B_REF = 0.5                    # crack-index saturation scale (B = 0.5 -> ci ~0.63)
# ROADMAP line 67: 9.0 (not 8.0) so band 0 'Failed' is REACHABLE at ci==1.0 —
# with 8.0 the band spanned 9..1 and 'Failed' was dead code.  ci 0 -> 9, ci 1 -> 0.
NBI_PER_CI = 9.0               # NBI spans 9 (excellent) .. 0 (failed) over ci 0..1
NBI_BANDS = [
    (9, "Excellent"), (8, "Very Good"), (7, "Good"), (6, "Satisfactory"),
    (5, "Fair"), (4, "Poor"), (3, "Serious"), (2, "Critical"),
    (1, "Imminent Failure"), (0, "Failed"),
]
SEVERITY_CUTS = ((0.15, "light"), (0.35, "moderate"), (0.60, "severe"), (1.01, "critical"))
RISK_CUTS = ((0.15, "A · low"), (0.35, "B · moderate"), (0.60, "C · high"), (1.01, "D · critical"))
MODEL_CONF = {"yolo-seg": 0.25, "heuristic": 0.10, "live-cv-subindex": 0.15}


def crack_index(dets: list[dict], cv_subindex: float | None = None,
                imaged_frac: float = 1.0) -> dict:
    """Aggregate crack burden -> saturating crack index (0..1).

    ``dets``: list of {conf, severity} detection dicts (models/cv/inference).
    ``cv_subindex``: if given (and no dets), the live cv sub-index is used as
    the crack index directly (labeled ``live-cv-subindex`` at the card level).
    ``imaged_frac``: fraction of the surface actually imaged — clamped to [0,1]
    (ROADMAP line 67: a caller passing 1.5 would otherwise report >100% imaged).
    """
    # ROADMAP line 67: validate imaged_frac — it is a FRACTION, so clamp to [0,1].
    imaged_frac = float(min(1.0, max(0.0, imaged_frac)))
    if cv_subindex is not None and not dets:
        ci = float(max(0.0, min(1.0, cv_subindex)))
        return {"ci": round(ci, 4), "burden": round(ci * B_REF, 4),
                "n_dets": 0, "imaged_frac": imaged_frac,
                "from": "live-cv-subindex"}
    burden = sum(float(d.get("conf", 0.0)) * float(d.get("severity", 0.0))
                 for d in dets)
    ci = 1.0 - float(np.exp(-burden / B_REF))
    return {"ci": round(ci, 4), "burden": round(burden, 4),
            "n_dets": len(dets), "imaged_frac": imaged_frac,
            "from": "segmentation"}


def severity_label(ci: float) -> str:
    for cut, label in SEVERITY_CUTS:
        if ci < cut:
            return label
    return SEVERITY_CUTS[-1][1]


def nbi_condition(ci: float) -> tuple:
    """(NBI 0-9, band label)."""
    nbi = int(min(9, max(0, round(9.0 - NBI_PER_CI * float(ci)))))
    return nbi, NBI_BANDS[9 - nbi][1]


def risk_class(ci: float) -> str:
    for cut, label in RISK_CUTS:
        if ci < cut:
            return label
    return RISK_CUTS[-1][1]


def confidence(mode: str, n_dets: int, ci: float) -> float:
    """Confidence grows with detector mode (model vs heuristic) + evidence
    (detection count, and a present index)."""
    base = float(MODEL_CONF.get(mode, 0.15))
    evidence = min(0.25, 0.05 * n_dets) if n_dets else 0.0
    has_signal = 0.05 if ci > 0.0 else 0.0
    return round(float(min(0.95, max(0.4, 0.5 + base + evidence + has_signal))), 2)


def condition_card(dets: list[dict] | None = None, cv_subindex: float | None = None,
                   mode: str = "yolo-seg", imaged_frac: float = 1.0,
                   frame_note: str = "") -> dict:
    """One honest condition card from the crack index.

    ``dets``         real segmentation detections (source=segmentation)
    ``cv_subindex``  live cv sub-index 0..1 (source=live-cv-subindex), used when
                     ``dets`` is empty/None so the card never hard-fails offline.
    ``mode``         detector mode for confidence: yolo-seg | heuristic | live-cv-subindex
    ``imaged_frac``  fraction of the surface imaged (clamped to [0,1])

    When BOTH ``dets`` and ``cv_subindex`` are absent the card is returned with
    source="no-evidence", nbi_label="No crack evidence detected" and a LOW
    confidence (0.2) — it never claims 'Excellent' @0.75 on zero data
    (ROADMAP line 67).
    """
    dets = dets or []
    if not dets and cv_subindex is None:
        # ROADMAP line 67: ZERO evidence — the old code returned NBI 9 'Excellent'
        # @ 0.75 confidence labeled 'segmentation' on an empty detection list.
        # NBI sits at the top band (no cracks measured) but the card says plainly
        # that nothing was measured, at low confidence.
        return {
            "source": "no-evidence",
            "crack_index": 0.0,
            "burden": 0.0,
            "severity": "no crack evidence",
            "condition": {"nbi": 9, "nbi_label": "No crack evidence detected",
                          "risk_class": RISK_CUTS[0][1]},
            "confidence": 0.2,
            "evidence": {"n_detections": 0,
                         "imaged_frac": round(float(min(1.0, max(0.0, imaged_frac))), 3)},
            "detector_mode": mode,
            "frame_note": frame_note,
            "note": ("No crack evidence was measured (no detections, no live cv "
                     "sub-index). NBI 9 here is the ABSENCE OF EVIDENCE, not a "
                     "certified 'Excellent' — never use it as a clearance. "
                     "Relative severity reading — NEVER a certified structural "
                     "assessment (models/fusion/condition.py)."),
        }
    idx = crack_index(dets, cv_subindex=cv_subindex, imaged_frac=imaged_frac)
    source = "segmentation" if (dets or idx["from"] == "segmentation") else "live-cv-subindex"
    if not dets and cv_subindex is not None:
        source = "live-cv-subindex"
    ci = idx["ci"]
    nbi, nbi_label = nbi_condition(ci)
    conf = confidence(mode if source == "segmentation" else "live-cv-subindex",
                      idx["n_dets"], ci)
    evidence = {"n_detections": idx["n_dets"],
                "imaged_frac": round(idx["imaged_frac"], 3)}
    if dets:
        # item 18: pixel-scale, UNcalibrated crack width from the real masks.
        # None when no detection has a measurable mask -> no width is claimed.
        w_agg = aggregate_width(dets)
        if w_agg is not None:
            evidence["crack_width"] = w_agg
    card = {
        "source": source,
        "crack_index": idx["ci"],
        "burden": idx["burden"],
        "severity": severity_label(ci),
        "condition": {
            "nbi": nbi,
            "nbi_label": nbi_label,
            "risk_class": risk_class(ci),
        },
        "confidence": conf,
        "evidence": evidence,
        "detector_mode": mode if source == "segmentation" else "live-cv-subindex",
        "frame_note": frame_note,
        "note": ("Relative severity reading from the crack index — NEVER a "
                 "certified structural assessment. NBI/risk-class are mapped "
                 "from the index on documented thresholds (models/fusion/"
                 "condition.py)."),
    }
    return card


def card_from_live_cv(cv_subindex: float | None) -> dict:
    """Card from the live fused cv sub-index (fast, offline-friendly)."""
    return condition_card(dets=None, cv_subindex=cv_subindex,
                          mode="live-cv-subindex",
                          frame_note="derived from the live fused cv sub-index")


if __name__ == "__main__":
    import json
    # segmentation example: 3 cracks, high conf
    dets = [{"conf": 0.92, "severity": 0.30},
            {"conf": 0.87, "severity": 0.22},
            {"conf": 0.60, "severity": 0.12}]
    print(json.dumps(condition_card(dets, mode="yolo-seg"), indent=1))
    print(json.dumps(card_from_live_cv(0.42), indent=1))
