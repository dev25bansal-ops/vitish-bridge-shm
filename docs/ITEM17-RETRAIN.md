# Item 17 — Scale+Temperature-Robust Retrain: Decision Gate Evidence

**Status: DECISION = NO-FLIP (2026-08-18).** The candidate ensemble does not clear
the gate-16 flip bounds. Shipped weights stay installed; the pinned demo arc is
untouched and every gate still passes. This doc records what was built, what was
measured, why the candidate failed, and the one experiment most likely to flip it.

§7.6 item 17: *"Temperature-invariant / scale-robust retrain so trained evidence
fires at demo scale (closes the pitch-vs-demo ML gap; flips gate-16 LEG C bound)."*

---

## What was built (committed `3461ee5`)

- **Inference threading** (`models/vibration/infer.py`): `AnomalyDetector` gained
  `set_temperature(T)` + a per-call `temperature=` override, threaded through the
  features-mode VAE/OCSVM covariate (feature 6, previously hardcoded 0.0).
  `backend/app/anomaly.py get_anomaly(.., temperature=None)` resolves the cached
  site temperature (real Open-Meteo or simulated fallback, never a network call)
  and forwards it. The LSTM-AE head reads `scale_norm:true` and RMS-normalizes
  its input, mapping demo-scale (~5e-2) and real-Z24 (~1e-3) into one range.
  This is backwards-compatible: shipped weights (`mode` unset / `scale_norm`
  absent) score exactly as before.
- **Retrain pipeline** (`tools/retrain_scale_temp.py`): assembles the healthy
  corpus (all Z24 labels {0,1,6}, channels 6/7/8 + the demo healthy family),
  applies **COORDINATED temperature-diagonal augmentation** — every healthy
  window time-stretched to each point of the thermal f1 grid
  `T ∈ {-5..35 °C}` and paired with *that* temperature — then trains a
  features-mode VAE + OCSVM + scaler and an RMS-normalized LSTM-AE.
- **Probe/decision tool** (`tools/probe_scale_temp.py`): measures the LEG C/D
  bounds against any weights dir and prints the flip verdict. Updated this
  session to query every window at its **implied temperature** (invert
  `f1(T) = f1_ref·(1 − α·(T−20))` for the window's measured peak frequency,
  clamped to the grid) — the physically-correct conditioning for a diagonal
  envelope.
- Candidate weights live only in gitignored `models/weights_scale_temp/` and
  `models/weights_scratch/` (the scratch dir is the earlier, abandoned
  DECOUPLED experiment). Nothing was installed into `models/weights/`.

## What was measured (full Z24, suite `test_deconfounding.py`, same bounds)

`trained_deviation` = envelope-relative push; bounds are the gate's own:

| LEG C (real Z24) / LEG D (demo) | shipped (2026-08-15 retrain) | candidate (coordinated diagonal) | flip / pass target |
|----------------------------------|------------------------------|----------------------------------|--------------------|
| label {0} (envelope's own state) max | **0.0000** ✓ | **0.1408** ✗ broke | < 0.02 |
| label {1} (documented confound) max | **0.3063** ✗ confound | **0.0000** ✓ removed | < 0.02 (flip) |
| label {6} (documented confound) max | **0.3712** ✗ confound | **0.1609** ✗ still deviates | < 0.02 (flip) |
| damaged mean | **0.1158** ✓ separates | **0.0000** ✗ no longer separates | ≥ 0.05 |
| demo raw (winter/summer/rupture) | 0.9803 / 0.9803 / 0.9803 (saturated) | 0.7058 / 0.7083 / 0.7338 | — |
| demo trained push (healthy **and** damage) | 0.0000 (floor-carried arc) | 0.0000 (still silent) | damage > 0.02 (flip) |

Suite verdicts: **shipped = PASS 0 failures** (floor legs 0.023–0.037 GREEN,
rupture fires 0.721/0.939). **candidate = FAIL 3 assertions** (label{0} broke,
damaged mean collapsed, demo-fire not achieved). The candidate removed the
label-{1} confound **only at the price of destroying the envelope's own-state
quiet and the entire damage separation** — strictly worse on the two properties
the demo actually depends on.

## Root cause (measured, not guessed)

The coordinated diagonal is only meaningful if each window can be paired with
the temperature whose **thermal first-mode frequency** matches its spectrum.
The pipeline and probe derive that from `features.extract_features(...)[1]`
= `peak_freq` = the **max-PSD bin**. On real Z24 windows that bin is *not* the
first mode — measured peak-freq p50 across the groups: label{0} **15.0 Hz**,
label{1} **0.39 Hz**, label{6} **12.4 Hz**, damaged **15.3 Hz** (single 1024
≈ 10.24 s windows have huge spectral variance; traffic/noise/lower-frequency
trends dominate the argmax). Inverting these gave implied temperatures of
−368…−498 °C clamping to the grid edges, so real windows landed off the
diagonal everywhere — healthy {0}/{6} "deviated" and damaged "stayed in".
The demo windows (clean pink+tonal resonance) do track their f1, which is why
LEG D behaved differently — but the real-data legs were conditioned on garbage.

A secondary issue: the VAE/OCSVM raw score is a logistic-squashed blend of
reconstruction-ratio and OCSVM margin compressed into [0,1], so genuine
off-diagonal distance is attenuated.

## Decision

**NO-FLIP.** SHIPPED weights remain installed. The pinned arc BHI
87.1 → 67.5 → 33.6 and all 19 gates are preserved (re-verified after the swap:
gate 16 PASS, sha256-verified weights restored). The item-17 goal ("trained
evidence fires at demo scale") remains OPEN with measured evidence.

Honesty notes: nothing was tuned to force any bound; the candidate's own
better number (label{1} = 0) is reported exactly as measured; the candidate
weights stay in the gitignored experiment dir for the next attempt.

## Next experiment (not run — the highest-evidence path to a real flip)

1. **Robust first-mode frequency tracking** for real windows: band-limited
   peak in the structural Z24 band (~2.5–6 Hz) on a multi-window averaged
   periodogram (the methodology the Z24 campaign itself used), replacing
   `peak_freq` for BOTH the augmentation pairing and the probe's implied-T.
2. **Widen `T_GRID` cold** to cover true cold-season health (real f1 up to
   ~4.6 Hz ⇒ T ≈ −10 °C), so no healthy mass sits edge-clamped.
3. Re-run retrain + probe + suite swap. Only a candidate that clears label{0},
   label{1}, label{6} < 0.02 AND damaged mean ≥ 0.05 AND demo-damage push
   > 0.02 — with `verify_demo_arc.py` re-pinned at freshly measured values —
   may be installed (a LEG-D flip changes the arc, so the re-pin is deliberate,
   not incidental).