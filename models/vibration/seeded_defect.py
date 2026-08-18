"""
Z24/S101-grounded seeded-defect model (D2-12) — "the damage is a physical seed".

The demo's damage scenario is no longer a generic "forced 4 Hz tonal that does
NOT shift the modal f1" (the honest-but-weak story).  It is now a **seeded
defect**: a named, physically-grounded progressive-damage step lifted from the
real benchmark campaigns, each of which reduces the flexural rigidity EI of a
specific span zone by N%.  The continuous 3-span Euler-Bernoulli FEM
(``models.vibration.stiffness``) then says exactly what the first natural
frequency f1 becomes, and the stream carries a modal resonance at that f1, so
the *measured* frequency shifts per the evidence — no magic, no forced tone.

Grounding (see vault/02-Research/Realistic-Digital-Twin §4):
  * **Z24** (Switzerland, 1998): the post-tensioned 14+30+14 m box girder was
    monitored through *progressive artificial damage* — pier settlement →
    concrete cracking / spalling → rupture of prestressing tendons.  Published
    modal tests (Maeck & De Roeck) show the eigenfrequencies drifting down a
    few % through the cracking stages and ~10%+ after tendon rupture.
  * **S101** (Austria, 2008): a full-scale steel-concrete composite bridge was
    tested to collapse by **saw-cutting through the main girder** — a severe,
    sharply-localized EI loss at one cross-section.

Each defect = a (span zone in x, max EI-loss fraction).  `progress` is a dict
{defect_key: 0..1} that scales each defect's loss (0 = untouched, 1 = full
severity).  The demo injector applies the Z24 sequence *in campaign order*
(settlement  -> cracking → tendon rupture) as the storyboard cross-fades, so f1
slides 3.80  -> ~3.2 Hz while BHI crosses into RED — the arc stays the guardrail.

Honesty notes:
  * The losses are CALIBRATED so the full Z24 sequence lands on f1 ~3.2 Hz
    (−15%): the deepest published Z24 damage state.  Each single defect is
    deliberately subtler (settlement alone ≈ −0.6%).
  * The S101 saw-cut is catalogued but NOT part of the demo sequence; it exists
    so the same module can describe either benchmark narrative honestly.
  * Per-span EI loss % is the SEEDED ground truth of the model, never a claim
    about the real bridge — it answers "what did we inject and where".
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from . import stiffness as physics
except ImportError:  # running as a bare script (python models/vibration/seeded_defect.py)
    import stiffness as physics

# --- catalog ------------------------------------------------------------------
@dataclass(frozen=True)
class Defect:
    key: str
    short: str            # compact overlay label
    name: str             # full campaign name
    source: str           # "Z24 benchmark" | "S101 benchmark"
    zone: Tuple[float, float]   # x-range (m) over which EI is reduced
    max_ei_loss: float    # fraction of EI removed at full severity (0..0.95)
    narrative: str        # what physically happened in the campaign


DEFECTS: Dict[str, Defect] = {
    "pier_settlement_cracks": Defect(
        key="pier_settlement_cracks",
        short="pier settlement -> cracks",
        name="Progressive pier settlement  -> cracking at the main-span support",
        source="Z24 benchmark",
        zone=(14.0, 20.0),   # main span adjacent to settled pier 1 (x = 14 m)
        max_ei_loss=0.18,
        narrative=("Z24: one pier was progressively lowered ~40 mm; the "
                   "resulting concrete cracking concentrated at the pier/span "
                   "junction, a small EI loss close to the support."),
    ),
    "midspan_concrete_cracking": Defect(
        key="midspan_concrete_cracking",
        short="mid-span concrete cracking",
        name="Concrete spalling / cracking at the main-span mid-span",
        source="Z24 benchmark",
        zone=(23.0, 35.0),   # main-span middle (the classic mid-span flexural zone)
        max_ei_loss=0.20,
        narrative=("Z24: concrete was spalled off and crack fans were cut at "
                   "the mid-span soffit — a growing mid-span flexural loss, "
                   "the first clear f1 drop of the campaign."),
    ),
    "tendon_rupture": Defect(
        key="tendon_rupture",
        short="tendon rupture",
        name="Rupture of prestressing tendons in the box girder",
        source="Z24 benchmark",
        zone=(24.0, 34.0),   # main-span, deeper loss (post-tensioning gone)
        max_ei_loss=0.45,
        narrative=("Z24: the campaign's final step — tendons cut in the box "
                   "girder web.  The deepest stiffness loss, pushing f1 down "
                   "~10%+ from healthy."),
    ),
    "girder_saw_cut": Defect(
        key="girder_saw_cut",
        short="girder saw-cut",
        name="Saw-cut through the main girder cross-section",
        source="S101 benchmark",
        zone=(28.5, 29.5),   # one sharp cross-section near mid-span
        max_ei_loss=0.85,
        narrative=("S101: the full-scale test bridge was saw-cut through the "
                   "main girder — a severe, sharply-localized EI loss at one "
                   "section (steel-concrete composite)."),
    ),
}

# The demo sequence — Z24's progressive damage IN CAMPAIGN ORDER.
Z24_SEQUENCE: List[str] = [
    "pier_settlement_cracks",
    "midspan_concrete_cracking",
    "tendon_rupture",
]
S101_SEQUENCE: List[str] = ["girder_saw_cut"]

# Staging thresholds: alpha 0..1 -> each Z24 defect reaches full severity in
# order (settlement in [0,.33], +cracking in [.33,.67], +tendon in [.67,1]).
_STAGE = (1.0 / 3.0, 2.0 / 3.0)


# PERF-04: the simulator re-evaluates the seeded-defect FEM every tick —
# _f1_now() (per current_window call, 3 nodes) AND seeded_state() (per tick)
# both call progress_from_alpha + f1_of_progress, each a full ~2ms FEM solve.
# That is ~4 FEM solves/tick even though the storyboard alpha changes smoothly
# (once per second at most).  A tiny alpha-keyed LRU serves repeat ticks from a
# cheap dict lookup; the demo's alpha is monotone, so the live working set is a
# handful of entries and the bounded cache stays a few KB.  Determinism is
# preserved: the memoised result is the exact FEM output for that alpha — the
# FEM itself is a pure function, so cache hit == recompute.  Frozen dict keys
# only (progress dicts are rebuilt per call and never mutated by callers).
@lru_cache(maxsize=256)
def _describe_cached(alpha: float, f1_base: float) -> Dict[str, float]:
    """Cached seeded-state narrative for one alpha. Pure: the FEM is a pure
    function of the defect progress, so this equals describe(progress)."""
    return describe(progress_from_alpha(alpha), f1_base=f1_base)


@lru_cache(maxsize=256)
def f1_from_alpha(alpha: float) -> float:
    """Cached FEM first-mode frequency for one storyboard alpha (PERF-04).

    The modal-resonance player asks for f1 once per emitted window (3 nodes →
    3 lookups/tick); each hit avoids a full FEM solve.  Bounded, deterministic,
    pure — identical to ``f1_of_progress(progress_from_alpha(alpha))``.
    """
    return f1_of_progress(progress_from_alpha(alpha))


def progress_from_alpha(alpha: float) -> Dict[str, float]:
    """Map a storyboard cross-fade alpha (0..1) to staged Z24 defect progress.

    Mirrors the Z24 campaign: settlement first (subtle), cracking next
    (the first real f1 drop), tendon rupture last (deep).  Returns a dict of
    {defect_key: progress 0..1}; healthy (alpha <= 0) -> empty.
    """
    a = float(max(0.0, min(1.0, alpha)))
    if a <= 0.0:
        return {}
    out: Dict[str, float] = {}
    for i, key in enumerate(Z24_SEQUENCE):
        lo = 0.0 if i == 0 else _STAGE[i - 1]
        hi = _STAGE[i] if i < len(_STAGE) else 1.0
        out[key] = min(1.0, max(0.0, (a - lo) / (hi - lo + 1e-12)))
    return out


# --- FEM evaluation -----------------------------------------------------------
def ei_profile(progress: Optional[Dict[str, float]] = None) -> np.ndarray:
    """Per-element EI (N·m²) with the applied defects folded in.

    Each element in a defect's zone loses `progress * max_ei_loss` of its
    rigidity (clamped ≤ 0.95).  `None`/empty -> the calibrated healthy EI.
    """
    p = np.full(physics.N_SEG, physics.EI_CAL)
    for key, prog in (progress or {}).items():
        d = DEFECTS.get(key)
        if d is None:
            continue
        loss = float(min(0.95, max(0.0, prog))) * d.max_ei_loss
        x0, x1 = d.zone
        for e in range(physics.N_SEG):
            xc = (e + 0.5) * physics.L_TOTAL / physics.N_SEG
            if x0 <= xc <= x1:
                p[e] *= (1.0 - loss)
    return p


def f1_of_progress(progress: Optional[Dict[str, float]] = None) -> float:
    """First vertical-mode frequency (Hz) under the seeded defect set."""
    return float(physics.fem_modes(ei_profile(progress), n_modes=1)[0][0])


def per_span_loss_pct(progress: Optional[Dict[str, float]] = None) -> List[float]:
    """Average EI-loss % per span (left / main / right: 0-14, 14-44, 44-58 m).

    This is the SEEDED ground truth — where and how much we reduced rigidity —
    reported so the overlay says "main span EI −N%" with a real number.
    """
    prof = ei_profile(progress)
    spans = ((0.0, 14.0), (14.0, 44.0), (44.0, 58.0))
    out = []
    for s0, s1 in spans:
        els = [e for e in range(physics.N_SEG)
               if s0 < (e + 0.5) * physics.L_TOTAL / physics.N_SEG < s1]
        base = sum(physics.EI_CAL for _ in els)
        cur = sum(float(prof[e]) for e in els)
        out.append(round(100.0 * (1.0 - cur / base), 1) if els else 0.0)
    return out


# --- honest description -------------------------------------------------------
def describe(progress: Optional[Dict[str, float]] = None,
             f1_base: Optional[float] = None) -> dict:
    """One self-describing payload for the API/twin overlay.

    Returns the active defects (progress > 0), the current FEM f1, its drift vs
    the (healthy) baseline, per-span EI loss %, a human label + source, and a
    plain-language honesty note.  `f1_base` defaults to the FEM healthy f1.
    """
    prog = {k: float(v) for k, v in (progress or {}).items() if v and v > 0}
    base = float(f1_base) if f1_base and f1_base > 0 else physics.F1_REF
    f1 = f1_of_progress(prog)
    # iterate the full catalog in a defined order (Z24 campaign sequence, then
    # S101) — NOT just Z24_SEQUENCE — so a pure-S101 progress dict (e.g.
    # {'girder_saw_cut': 1.0}) is described correctly (ROADMAP line 43).
    ordered = Z24_SEQUENCE + S101_SEQUENCE + [k for k in prog if k not in DEFECTS]
    active = [{"key": k, "short": DEFECTS[k].short, "source": DEFECTS[k].source,
               "progress": round(prog[k], 3),
               "ei_loss_pct": round(prog[k] * DEFECTS[k].max_ei_loss * 100.0, 1),
               "zone": list(DEFECTS[k].zone)}
              for k in ordered if k in DEFECTS and k in prog and prog[k] > 0]
    # dominant = the defect with the worst current EI loss (physical severity);
    # latest = the campaign step just seeded (narrative position).
    dominant = (max(active, key=lambda a: a["ei_loss_pct"]) if active else None)
    latest = (active[-1] if active else None)
    per_span = per_span_loss_pct(prog)
    label = (f"{dominant['short']}" if dominant else "none")
    return {
        "model": "z24 continuous 3-span box girder (14+30+14 m), EI-seeded defects",
        "active": active,
        "dominant_key": dominant["key"] if dominant else None,
        "dominant": dominant,
        "latest": latest,
        "label": label,
        "source": dominant["source"] if dominant else None,
        "sequence": list(Z24_SEQUENCE),
        "f1": round(f1, 3),
        "f1_ref": round(base, 3),
        "f1_drift_pct": round(100.0 * (f1 / base - 1.0), 2),
        "ei_loss_pct": round(max(per_span), 1),       # worst-span seeded loss
        "per_span_loss_pct": per_span,
        "note": ("seeded model defect -- EI reduced by the demo scenario, not a "
                 "certified rating of the real bridge"),
    }


def overview() -> dict:
    """Alias for API symmetry with the stiffness snapshot (no progress = healthy)."""
    return describe({})


if __name__ == "__main__":
    import json
    for alpha in (0.0, 0.33, 0.5, 0.67, 0.85, 1.0):
        p = progress_from_alpha(alpha)
        d = describe(p)
        print(f"alpha {alpha:.2f}: f1 {d['f1']} Hz  drift {d['f1_drift_pct']:+.2f}%  "
              f"label={d['label']!r}  span {d['per_span_loss_pct']}")
    print(json.dumps(describe(progress_from_alpha(1.0)), indent=2))
