---
tags: [demo, ml, shm, vitish-2026, deconfounding]
created: 2026-08-15
---

# Environmental De-confounding Study (§117)

**Question:** can the detector tell *temperature* apart from *damage*? The Z24
benchmark's first vertical frequency wanders ~14.5% peak-to-peak over a year
with air temperature (3.1 °C winter ↔ 27.0 °C summer → f1 4.175 ↔ 3.645 Hz).
Thermal wandering is the **#1 false-damage source** in vibration-based SHM: a
cold snap can look exactly like stiffness loss. This study measures whether the
SHIPPED detector fires on temperature-only — it must not.

**Deterministic experiment:** a controlled seasonal sweep where the **only
varying quantity is f1** (via the Z24-anchored thermal model
`models/vibration/temperature.py`). The pink-noise base realization is fixed
(`np.random.default_rng(999)`); every window differs from its neighbours only by
the thermal f1 of its day-of-year. Torch/numpy are seeded per block. Gate:
`backend/tests/test_deconfounding.py` (gate 16, 11 checks) — the numbers below
are re-measured on every run, not recalled.

| Leg | What | Measured (2026-08-15) | Bound | Verdict |
|-----|------|----------------------|-------|---------|
| A | Floor score, seasonal f1 sweep, **fixed noise** | max **0.037** (winter 0.023 → summer 0.037) | < 0.20 GREEN | ✅ no thermal false alarm |
| B | Floor fires on seeded rupture @ both extremes | **0.721** winter / **0.939** summer | > 0.50 | ✅ separation, not blindness |
| C | Trained ensemble @ real Z24 scale | healthy{0,1} dev max **0.0000**; damaged mean **0.1158** | healthy < 0.02; damaged ≥ 0.05 | ✅ real damage separates |
| C′ | Trained ensemble @ real Z24 scale — **later-campaign healthy label {6}** | dev mean **0.0956**, max **0.3715** | documented | ⚠️ the honest limit (below) |
| D | Trained ensemble @ demo scale (RMS ~0.05) | raw score **0.9803 constant** for healthy AND damage; push **0.0000** | push < 0.02 | ⚠️ floor-carried (below) |

## What this proves

1. **The deterministic floor is de-confounded.** Across a full-year f1 sweep on a
   fixed noise realization, the floor never exceeds 0.037 — comfortably GREEN
   (the 0.35 healthy refit cap) and ~9× below it. The same floor fires at 0.72–
   0.94 on the seeded rupture at *both* seasonal extremes. Flat-on-temperature,
   loud-on-damage: that is the de-confounding property a deployed system needs.

2. **The demo arc is carried by the floor.** At demo scale (RMS ~0.05) the
   trained raw score is **amplitude-saturated** — a constant 0.9803 for healthy
   *and* damaged windows (the scaler was fit on real Z24 at RMS ~5e-5; the
   synthetic stream saturates it). The healthy envelope absorbs the constant, so
   `trained_push = max(0, raw − envelope_hi − margin) = 0` for everything. This
   is *why* the 2026-08-15 retrain could not and did not break the pinned arc
   (BHI 87.1 → AMBER 67.5 → RED 33.6): at demo scale the trained path is
   invisible by amplitude, by construction.

## The honest limits (documented, not hidden)

- **Label {6} confounding (Leg C′).** Z24's healthy label set is not stationary:
  later-campaign healthy recordings (label {6}, ~10 months in) deviate from the
  healthy envelope like damage (max 0.3715, mean 0.0956) even though they are
  healthy. The trained envelope is therefore **NOT season/state-agnostic**. This
  is pinned in the gate as a *must-stay-documented* finding: a season-agnostic
  retrain (temperature-normalized features + healthy training covering the full
  seasonal envelope) must bring healthy-label-{6} deviation below 0.02 — at
  which point gate 16's assertion flips to that bound.
- **Demo-scale trained inertness (Leg D).** The trained path contributes ~0 at
  demo scale *by amplitude*. It separates real damage only at real Z24 scale
  (Leg C). This is stated plainly to judges: the demo's trained story is "real
  separation exists, proven on real Z24 data," and the live synthetic stream is
  a floor-carried demonstration of the *deployment* concept — not a claim that
  the trained models run the demo's arc.

## Mitigation path (feasible, not yet built)

- Temperature-normalize the 7 trained features (peak_freq, spectral_centroid are
  thermal-sensitive) → `models/vibration/features.py` + retrain covering the
  full seasonal healthy envelope (Z24 labels {0,1,6} already span ~10 months of
  seasons — label {6} *is* the seasonal data needed).
- Per-structure-type retraining on HBTA (full-scale steel bridge, 30+ imposed
  damage states, CC-BY-4.0) would add a second structural family to the healthy
  envelope. See [[PostHackathon-Prep]] §117.

## Run it

```bash
python backend/tests/test_deconfounding.py     # 11 checks
bash scripts/verify_gate.sh                     # gate 16/16
```

Related: [[Metrics]] · [[Key-Decisions]] #11 · [[PostHackathon-Prep]] #117
