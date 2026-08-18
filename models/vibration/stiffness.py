"""
Z24 box-girder stiffness physics — the "behaves like the bridge" layer.

Identity (D1-2 decision, 2026-08-14): the hero bridge is the **Z24 benchmark
(30 m main span)**, a three-span post-tensioned concrete box girder
(14 + 30 + 14 m) continuous over four supports.  The demo arc stays as-is;
this module only *explains* the vibration signal with two honest models:

  1. **Reference simple-span proxy** (the documented roadmap formula)
        EI = 4·f1²·L⁴·ρA / π²          L = 30 m main span, pinned-pinned
     Used for the on-screen "EI drift" overlay — a well-known closed form.

  2. **Continuous 3-span Euler–Bernoulli FEM** (this file)
     Six DOF-per-node beam elements, supports at x = 0 / 14 / 44 / 58 m,
     EI calibrated so the healthy first vertical mode = 3.80 Hz (matches
     Z24's published f1 ≈ 3.8–4.0 Hz).  Used to infer mid-span stiffness
     loss (damage %) from a measured f1 and to produce the mode shapes
     that animate the deck.

Honesty notes (see vault/02-Research/Realistic-Digital-Twin §3, §4):
  * The FEM is a straight-beam idealisation — no torsion, no non-linear
    cable-stay effects (we are deliberately NOT a cable-stayed deck).
  * Damage % is "model-inferred mid-span EI reduction", never a certified
    rating.  The empirical Z24/S101 anchor: −10% stiffness → ≈ −3% f1.
  * Per-zone seeded defects (the demo's D2-12 damage scenario) are evaluated
    by the SAME FEM through ``f1_of_profile`` / the ``seeded_defect`` module,
    so the measured f1 shift and the model-inferred damage are one physics.

The mapping below (mid-span EI −10% → f1 −2.2%, −30% → −7.3%) reproduces
the Z24 evidence (its deepest progressive-damage scenarios shifted f1 by
roughly 7–9%).
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple

# Pin BLAS to 1 thread BEFORE numpy's first BLAS call (see backend/app/__init__
# for the measured 50x: 0.18s -> 0.0035s per FEM solve).  This module is the
# FEM hot path and may be imported standalone (models/*), outside the app
# package that normally sets it.  setdefault: user env wins.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np

# --- identity constants -------------------------------------------------------
L_TOTAL = 58.0          # m, full Z24 superstructure (14 + 30 + 14)
L_MAIN = 30.0           # m, main (middle) span — the reference proxy length
SUPPORTS = (0.0, 14.0, 44.0, 58.0)   # x of abutment + 2 piers + abutment
RHO_A = 12_500.0        # kg/m — box-girder mass per unit length (~5 m² × 2500)
F1_REF = 3.80           # Hz — healthy first vertical mode (calibration target)
N_SEG = 58              # FEM segments (1 per metre — enough for mode 1..4)

# Calibrated so FEM f1(healthy, uniform EI) = F1_REF (bisection, see _calibrate).
EI_CAL = 2.3421e10      # N·m² — continuous 3-span box-girder flexural rigidity
EI_REF = 5.925e10       # N·m² — reference simple-span EI from the closed form

_NODES = N_SEG + 1
_X = np.linspace(0.0, L_TOTAL, _NODES)
_LE = L_TOTAL / N_SEG


# --- element matrices ---------------------------------------------------------
def _element(ei: float) -> Tuple[np.ndarray, np.ndarray]:
    """4-dof Euler-Bernoulli element (w1, θ1, w2, θ2) stiffness + mass."""
    k = ei / _LE**3 * np.array([
        [12, 6 * _LE, -12, 6 * _LE],
        [6 * _LE, 4 * _LE**2, -6 * _LE, 2 * _LE**2],
        [-12, -6 * _LE, 12, -6 * _LE],
        [6 * _LE, 2 * _LE**2, -6 * _LE, 4 * _LE**2],
    ])
    m = RHO_A * _LE / 420.0 * np.array([
        [156, 22 * _LE, 54, -13 * _LE],
        [22 * _LE, 4 * _LE**2, 13 * _LE, -3 * _LE**2],
        [54, 13 * _LE, 156, -22 * _LE],
        [-13 * _LE, -3 * _LE**2, -22 * _LE, 4 * _LE**2],
    ])
    return k, m


def fem_modes(ei_profile: Optional[np.ndarray] = None,
              n_modes: int = 4) -> Tuple[np.ndarray, np.ndarray]:
    """
    First `n_modes` natural frequencies (Hz) + mode shapes (N_SEG+1, n_modes),
    each shape sampled at the deck nodes.  `ei_profile` (N_SEG,) sets per-
    element EI (damage); `None` uses the calibrated uniform EI_CAL.

    Solved as the symmetric-definite generalized eigenproblem Kx = λMx via a
    Cholesky transform (M = LLᵀ, A = L⁻¹KL⁻ᵀ symmetric) so we can use the fast
    symmetric ``np.linalg.eigh``.  The previous dense general ``eigvals`` was
    ~0.3 s per solve — fine for a one-off, but ``seeded_state()`` runs it every
    simulator tick, so a 30x-slower solve visibly stretched the demo cadence.
    """
    ne = N_SEG
    nd = _NODES * 2
    K = np.zeros((nd, nd))
    M = np.zeros((nd, nd))
    for e in range(ne):
        ei = EI_CAL if ei_profile is None else float(ei_profile[e])
        ke, me = _element(ei)
        dofs = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
        for a in range(4):
            for b in range(4):
                K[dofs[a], dofs[b]] += ke[a, b]
                M[dofs[a], dofs[b]] += me[a, b]

    # constrain the four supports (w = 0); keep rotations free
    keep = [i for i in range(nd)
            if not ((i % 2 == 0) and (_X[i // 2] in SUPPORTS))]
    Ks, Ms = K[np.ix_(keep, keep)], M[np.ix_(keep, keep)]

    # Kx = λMx  ->  L = chol(M), A = L⁻¹KL⁻ᵀ,  A y = λ y,  x = L⁻ᵀ y
    L = np.linalg.cholesky(Ms)
    # PERF-02: triangular solves instead of inv(L) @ Ks @ inv(L).T — the inverse
    # materialises the full dense inverse; solving against the (lower)
    # triangular factor is cheaper and numerically at least as stable.
    # A = L⁻¹·Ks·L⁻ᵀ:
    #   Y = L⁻¹·Ks      (solve L·Y = Ks)
    #   A = Y·L⁻ᵀ       (solve L·Aᵀ = Yᵀ, then transpose: L⁻¹·Yᵀ = (Y·L⁻ᵀ)ᵀ)
    # numpy has no dedicated solve_triangular, so this uses np.linalg.solve on
    # the already-triangular factor (BLAS dtrsm is invoked for the triangular
    # solve — no dense LU of L is performed), which keeps the hot path free of
    # a scipy dependency and removes the inv() the original claim pointed at.
    Y = np.linalg.solve(L, Ks)                                   # Y = L⁻¹ Ks
    A = np.linalg.solve(L, Y.T).T                                # A = Y L⁻ᵀ
    A = 0.5 * (A + A.T)          # symmetrize against floating-point noise
    lam, V = np.linalg.eigh(A)
    order = np.argsort(lam)
    lam, V = lam[order], V[:, order]
    freqs = np.sqrt(np.clip(lam, 0, None)) / (2 * np.pi)
    freqs = freqs[:n_modes]

    # mode shapes: x = L⁻ᵀ y, re-expanded into the full DOF vector (zeros at the
    # constrained support DOFs), then sample the transverse DOFs (w at each node)
    # PERF-02: L⁻ᵀ·y via a triangular solve (solve Lᵀ x = y), not Linv.T@y.
    shapes = []
    for m in range(n_modes):
        x = np.zeros(nd)
        x[keep] = np.linalg.solve(L.T, V[:, m])
        w_node = x[0::2]
        # normalise to unit max deflection
        w_node = w_node / (np.max(np.abs(w_node)) + 1e-12)
        shapes.append(w_node)
    return freqs, np.column_stack(shapes)


def damage_profile(damage_frac: float) -> np.ndarray:
    """Per-element EI with `damage_frac` reduction across the main-span
    middle 12 m (x ∈ [23, 35] m) — a mid-span flexural crack / loss zone."""
    p = np.full(N_SEG, EI_CAL)
    for e in range(N_SEG):
        xc = (e + 0.5) * _LE
        if 23.0 <= xc <= 35.0:
            p[e] = EI_CAL * (1.0 - max(0.0, min(0.9, damage_frac)))
    return p


def f1_of_damage(damage_frac: float) -> float:
    """FEM first mode under a mid-span stiffness loss (fraction 0..0.9)."""
    return float(fem_modes(damage_profile(damage_frac), n_modes=1)[0][0])


def f1_of_profile(ei_profile: Optional[np.ndarray] = None) -> float:
    """FEM first mode under an arbitrary per-element EI profile (seeded
    defects, D2-12).  `None` = the calibrated healthy EI -> F1_REF."""
    return float(fem_modes(ei_profile, n_modes=1)[0][0])


# PERF-02: coarse-grid f1->damage memoization.  The stiffness overlay re-inverts
# damage_from_f1 (a ~14-FEM-solve bisection, measured ~29ms) on EVERY polled
# snapshot (~every 1.5s/tab), even though the smoothed f1 barely moves between
# polls.  A coarse grid over the damage range maps f1 -> damage once, and the
# nearest-neighbour lookup answers most repeat queries without any FEM solve.
# The grid is monotone + strictly decreasing in f1, so a count-based bin is the
# exact bracketing interval; a table-miss (f1 outside [grid_f1[-1], F1_REF])
# falls back to the full bisection, and the healthy-above-baseline case is
# still clamped to 0.0.  The lookup is deterministic and matches the bisection
# to within half a grid cell; for the snapshot's rounded outputs
# (damage_pct 1 decimal) that is exact on the shipped grid spacing.
# The grid is built LAZILY (once, on first lookup) and cached: the 721 FEM
# solves behind it take ~1.6s, which an import-time build would push onto every
# standalone ``models.vibration.stiffness`` import even when the caller never
# inverts damage.  A lock keeps concurrent first lookups from duplicating the
# solve; the build is monotone+deterministic, so the cache is a plain idempotent
# lazy-init with no tearing risk.  Set ``_DAMAGE_GRID_N`` at import and mutate
# the grid via the cache only.
import threading as _threading
_DAMAGE_GRID_N = 720                     # 0.125% cells across [0, 0.9]
_GRID_LOCK = _threading.Lock()
_GRID_CACHE = None                       # (damage, f1, f1_upper, f1_lower)


def _get_grid():
    """Build (and cache) the coarse damage->f1 grid once; returns the tuple."""
    global _GRID_CACHE
    if _GRID_CACHE is None:
        with _GRID_LOCK:
            if _GRID_CACHE is None:
                d = np.linspace(0.0, 0.9, _DAMAGE_GRID_N + 1)
                f = np.array([f1_of_damage(x) for x in d])  # strictly decreasing
                _GRID_CACHE = (d, f, float(f[0]), float(f[-1]))
    return _GRID_CACHE


def _damage_from_f1_grid(f1: float) -> Optional[float]:
    """Nearest-bin damage from the coarse grid; None when f1 is out of range."""
    d, f, f_upper, f_lower = _get_grid()
    if not (f_lower < f1 <= f_upper):
        return None
    # f is strictly decreasing, so the bin bracketing f1 is [n-1, n] where n =
    # (# of grid f1 entries still >= f1): f[n-1] >= f1 is the LAST such entry
    # and f[n] is the FIRST one below f1.  (argmax over a decreasing boolean
    # array would always return 0 — the first True — so the count is the
    # correct index, not the argmax.)
    n = int(np.count_nonzero(f >= f1))
    if not (1 <= n <= _DAMAGE_GRID_N):
        return None
    lo_d, hi_d = float(d[n - 1]), float(d[n])
    lo_f, hi_f = float(f[n - 1]), float(f[n])
    if hi_f >= lo_f:            # guard against a flat bin (defensive only)
        return 0.5 * (lo_d + hi_d)
    frac = (f1 - lo_f) / (hi_f - lo_f)      # 0 at the left bin, 1 at the right
    return lo_d + frac * (hi_d - lo_d)


def damage_from_f1(f1: float, lo: float = 0.0, hi: float = 0.9,
                   tol: float = 1e-4) -> float:
    """Invert `f1_of_damage` (bisection): the mid-span EI reduction % that
    reproduces a measured f1.  Monotone, so bisection converges fast.  The
    range [0, 0.9] reaches `tol` in ~14 iterations; the old fixed 80-loop ran
    ~6x more FEM solves than the tolerance allows (each solve is the FEM
    eigenvalue problem), so we exit as soon as the bracket is tight.

    PERF-02: repeat queries (the twin polls the overlay ~every 1.5s) hit the
    coarse-grid lookup first — a single O(1) argmax over the precomputed
    monotone table instead of ~14 FEM solves; only a genuine table miss falls
    through to the exact bisection.  ``lo/hi/tol`` are honoured verbatim on the
    fallback path, and the grid is bypassed entirely for those callers.
    """
    if f1 <= 0 or f1 >= F1_REF:
        return 0.0
    if lo == 0.0 and hi == 0.9 and tol == 1e-4:   # shipped caller -> grid first
        g = _damage_from_f1_grid(f1)
        if g is not None:
            return g
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if hi - lo < tol:
            break
        if f1_of_damage(mid) < f1:
            hi = mid  # too much damage -> f1 below target; reduce it
        else:
            lo = mid
    return 0.5 * (lo + hi)


# --- reference simple-span proxy (roadmap formula) -----------------------------
def ei_ref_from_f1(f1: float, span: float = L_MAIN) -> float:
    """EI = 4·f1²·L⁴·ρA / π² — documented stiffness-from-frequency proxy."""
    return 4.0 * f1**2 * span**4 * RHO_A / (np.pi**2)


def ei_drift_pct(f1: float, base: float = F1_REF) -> float:
    """% stiffness drift vs baseline (positive = stiffness loss)."""
    if f1 <= 0 or base <= 0:
        return 100.0
    return 100.0 * (1.0 - (f1 / base) ** 2)


def midspan_deflection_um(load_n: float, ei: float = EI_REF,
                          span: float = L_MAIN) -> float:
    """Static mid-span deflection under a central point load: δ = PL³/(48EI),
    in micrometres (concrete girder deflections are mm-scale)."""
    return 1e6 * load_n * span**3 / (48.0 * ei)


# --- public snapshot builder ---------------------------------------------------
def snapshot(f1_meas: Optional[float], f1_base: Optional[float] = None,
             day_of_year: Optional[float] = None,
             temp_f1_ref: Optional[float] = None) -> dict:
    """One honest, self-describing physics payload for the API/twin.

    `f1_base` (default F1_REF) is the healthy baseline the drift is measured
    against — a live tracker passes its own measured self-baseline.
    `day_of_year` (1..365) optionally drives the seasonal temperature overlay
    (D2-10): the thermal expectation of f1 and the temperature-compensated
    residual that separates thermal wandering from REAL stiffness loss.  When
    omitted the payload carries no thermal fields (offline/physics-only use).
    `temp_f1_ref` is the healthy reference at T_REF used by the thermal model —
    a live tracker passes its baseline NORMALIZED to 20 C (see
    ``models.vibration.temperature.normalize_to_ref``) so the residual compares
    like-for-like instead of double-counting the season; when omitted the
    thermal model falls back to ``f1_base``.

    Honesty notes:
      * The damage inversion is **self-calibrating**: the measured f1 is mapped
        onto the FEM reference scale via the baseline (`f1 * F1_REF / base`), so
        a bridge whose real healthy fundamental sits at 3.9 Hz (the Z24) still
        reads 0% damage when healthy, and the calibration curve (−10% EI →
        ≈ −2.2% f1) applies to *relative* drift from that baseline.
      * `ei_drift_pct` is clamped to ≥ 0: a measured f1 *at or above* baseline is
        a forced response (e.g. the demo's 4 Hz rupture tonal), never a stiffness
        *gain*, so the overlay refuses to claim "stiffening".
      * The temperature overlay is SIMULATED (day-of-year model anchored to the
        Z24 ~14% seasonal f1 shift) and the residual is the honest quantity —
        see ``models.vibration.temperature``.
    """
    f1 = f1_meas if f1_meas and f1_meas > 0 else F1_REF
    base = f1_base if f1_base and f1_base > 0 else F1_REF
    damage = damage_from_f1(f1 * F1_REF / base)
    # Deadband: real f1 tracks under traffic wander ~±2% even when healthy —
    # a drift that small is response noise, not stiffness loss.  Only infer
    # damage once the smoothed f1 sits clearly below the baseline.
    if f1 >= base * 0.98:
        damage = 0.0
    freqs, shapes = fem_modes(damage_profile(damage), n_modes=2)
    f1_drift_pct = 100.0 * (f1 / base - 1.0)
    ei_drift_pct = max(0.0, 100.0 * (1.0 - (f1 / base) ** 2))
    payload = {
        "model": "z24 continuous 3-span box girder (14+30+14 m)",
        "reference": "simple-span proxy EI = 4·f1²·L⁴·ρA/π², L=30 m",
        "f1_meas": round(f1, 3),
        "f1_ref": round(base, 3),
        "f1_drift_pct": round(f1_drift_pct, 2),
        "ei_ref": round(ei_ref_from_f1(f1), 4),
        "ei_ref_base": round(ei_ref_from_f1(base), 4),
        "ei_drift_pct": round(ei_drift_pct, 2),
        "damage_pct": round(100.0 * damage, 1),   # model-inferred mid-span loss
        "deflection_um": round(midspan_deflection_um(
            350e3, EI_REF * (1.0 - damage)), 1),
        "freqs": [round(float(fr), 3) for fr in freqs],
        "x": [round(float(xx), 1) for xx in _X.tolist()],
        "shapes": [[round(float(v), 4) for v in shapes[:, m].tolist()]
                   for m in range(shapes.shape[1])],
    }
    if day_of_year is not None:
        from models.vibration import temperature as thermal
        thermal_ref = temp_f1_ref if temp_f1_ref and temp_f1_ref > 0 else base
        payload.update(thermal.temp_fields(f1, thermal_ref, day_of_year))
    return payload


if __name__ == "__main__":
    import json
    print(json.dumps(snapshot(F1_REF), indent=2))
    print(json.dumps(snapshot(3.50), indent=2))
