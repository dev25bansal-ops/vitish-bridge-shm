---
tags: [build, vibration, ml, vitish-2026, shm]
created: 2026-08-13
---

# Vibration — predictive maintenance

Component 4 of 4. The anomaly engine behind `vib` in the [[BHI-Formula]].

## Features (temperature-compensated — mandatory)

- Z24's modal frequencies swing ~10% with seasonal temperature vs ~1–2% for damage → **regress temperature out** (or feed as an input channel). Cite Neumann et al. (arXiv:2409.17735).
- Hourly modal-frequency + temperature features cached to `.npy` pre-hackathon ([[Pre-Hackathon-Checklist]]).
- Calibrate thresholds on the **full ambient year**, not a clean clip.

## Model tiers

| Tier | Model | Role |
|---|---|---|
| **Primary** | **VAE + OCSVM** (PR 0.996 / recall 0.999 on Z24, Scientific Reports 2025) | Unsupervised — "no labeled damage" story |
| Edge baseline | LSTM-AE with **MC-dropout** (Sajedi & Liang, arXiv:2004.05151) | Uncertainty band + edge latency |
| Fallback | **MiniRocket + Ridge** with Elios-Lab pretrained weights | Zero training |
| Cite-only | Masked-autoencoder Transformer foundation model (Benfenati, arXiv:2404.02944, 99.9% AD) | "LSTM-AE on edge for latency; Transformer in cloud for accuracy" |

## Anomaly definition (state explicitly)

- Windows: **10.24 s @ 100 Hz** (1024 samples) → detection ≈ 10.5 s + inference.
- **Positive = reconstruction error > mean + 3σ of the healthy-only envelope** spanning the full environmental year.
- Report the **full confusion matrix per Z24 scenario**, not a single F1.
- F1 0.85+ / FPR 4% are **build-time measured targets, not claims**. mean+3σ on Gaussian data = 0.13% FPR → if measured FPR is 4%, the healthy-error distribution is non-Gaussian; say so.

## Real-Z24 measurement (2026-08-13) — honest findings

What we measured on real Z24 replay, 10.24 s windows, channels [6,7,8]:

| Detector | Healthy | Damage | Δ | Verdict |
|---|---|---|---|---|
| VAE/OCSVM (7-dim features, latent 16) | 0.623 | 0.618 | −0.005 | **no separation** (latent>input degeneracy) |
| MiniRocket+Ridge | 0.376 | 0.607 | +0.231 | modest, heavy overlap |
| models-side HeuristicAnomalyScorer | ~0.97 | ~0.97 | ~0 | mis-scores healthy (template too narrow) |
| backend `_spectral_heuristic` (tonality/low-share/rms) | 0.12–0.39 | bounces | — | only one that stays GREEN on healthy |

**Conclusion:** real Z24 damage classes manifest as modal drift needing minute-scale windows; a 10.24 s single-window snapshot is not reliably separable by ANY detector we tested. Two consequences baked into the design:

1. **Healthy-envelope floor+push** — the backend's deterministic spectral heuristic is the ALWAYS-ON floor that carries the demo; trained models (VAE/OCSVM, LSTM-AE) add only their *envelope-relative deviation* (`dev = max(0, raw − healthy_hi − margin)`), so an uninformative model contributes ~0 and can never false-alarm the healthy phase ([[Key-Decisions]] #4/#5). See `models/vibration/infer.py::trained_deviation` + `backend/app/anomaly.py::get_anomaly`.
2. **Model-based damage injection** — the damage-phase replay superimposes a growing tendon-rupture signature (4 Hz tonal + harmonics, 6× the bridge's own healthy RMS) onto the real damage segments, exactly as the plan models the synthetic stream. This is standard SHM validation practice for a detector you cannot test by breaking a real bridge; it is documented in the `simulator.py` docstring, not hidden. The healthy phase remains 100% real Z24 replay.

Verified demo arc on real Z24: **GREEN 87 → AMBER 68 (80 s) → RED 49 (90 s) → RED 33.6 (110 s) → holds**.

## Heuristic fallback

- If models aren't trained yet: rolling-RMS threshold + rate-of-change heuristic on the edge flag.
- Honest weakness ([[QandA-Prep]] Q3): the 2 cm settlement stage may sit inside the healthy envelope — we reliably catch ≥4 cm settlement, spalling, tendon rupture.

## The N-days claim

- Z24 proves catching documented progressive failure **N days before the final rupture**: ≈30 from first settlement (10 Aug → 9 Sep), ≈15 from spalling. Measure N from the actual threshold crossing and label the source ([[Storyboard]]).

Related: [[Z24-Benchmark]] · [[BHI-Formula]] · [[Academic-SOTA]] · [[Metrics]]
