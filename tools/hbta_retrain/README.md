# HBTA per-structure retrain — train on the internal server

Full-scale **steel truss** bridge (Hell Bridge Test Arena, HBTA, CC-BY-4.0) — a
second structural family beyond the Z24 box girder. The repo's trained
vibration ensemble was built on Z24; this retrains the SAME pipeline on HBTA's
**undamaged phase** (UDS recordings) and checks that the trained envelope
separates HBTA's **imposed-damage states** (DS1..DS8). This is PostHackathon
§117's *per-structure-type retraining* — evidence the trained path generalizes,
not just overfits one bridge.

Everything is in this tar (`data_100Hz.h5` 2.4 GB + prep/train/verify + the
`models/vibration` package). No other repo files are needed.

## 1 · Copy + extract on the server

```bash
# copy the tar over (internal network):
scp hbta_retrain_2026-08-15.tar.gz nvidia@<server>:~/
tar xzf hbta_retrain_2026-08-15.tar.gz
cd hbta-retrain
```

## 2 · One command (two lanes)

```bash
# inside a venv with torch+CUDA (your fignn_env works):
conda activate fignn_env        # or: source <venv>/bin/activate
bash run_retrain.sh
```

That runs, in order: prep (h5 → windows) → train VAE/OCSVM → train LSTM-AE →
verify separation by severity, for **both** sensor families:

| Lane | Channels | VAE mode | Expected verdict (measured locally) |
|------|----------|----------|--------------------------------------|
| ACCEL | 18 global accelerometers (AG, y/z) | raw 1024 | **CHECK** — damage not visible at 10.24 s |
| STRAIN | 15 strain gages (SB lower-chord, SC cross-girders) | features 7-dim | **CHECK** — score-level; feature-level: RMS mean drops ~50%, not 2σ-clean |

Outputs land in `hbta_accel_weights/` and `hbta_strain_weights/`.

Optional knobs (env vars): `HBTA_CHANNELS=strain` (only the strain lane),
`HBTA_VAE_EPOCHS`, `HBTA_LSTM_EPOCHS`. Each lane is also runnable standalone —
see the `run_retrain.sh` header for the exact commands.

## 3 · What the verify line means (honest)

`verify_hbta.py` warms the healthy envelope on **healthy (UDS)** windows, then
measures `trained_deviation` (the shipped envelope-floor+push score) on healthy
vs **damaged** windows per severity DS1..DS8, and prints **two levels of
evidence**:

- **score-level table** — healthy dev ≈ 0 → envelope absorbs the undamaged
  bridge; damaged dev > 0 rising with severity → the trained path sees the
  imposed damage. **Measured locally: damaged dev means are 0.000–0.002 on both
  lanes (max 0.099 at DS7). Verdict CHECK.** The Z24-fit envelope has a
  fat-tailed healthy raw distribution (max 0.892) that absorbs every damaged
  window; HBTA's imposed damage does not rank above the healthy ceiling.
- **feature-level table** (per sensor family, when prep's channel provenance is
  present) — raw window `rms` and `peak_freq`, healthy mean±std with 2σ band,
  per severity, marked when a severity mean leaves the band. **Measured
  locally: strain RMS mean drops ~50% per severity in BOTH families (SB
  0.113→0.052–0.073; SC 0.125→0.046–0.061) but healthy RMS spread is large
  (CV≈50%), so no severity mean clears the 2σ band — a weak, not clean,
  separation. `peak_freq` does not separate** (quasi-static noise floor for
  strain).
- **RMS reference monitor** (per sensor family) — a minimal feature-level
  detector, explicitly NOT the trained path and NOT the gate: it warms a
  healthy RMS **p5 lower envelope** on a stratified sample of healthy windows
  (every k-th family window, so it spans all recordings — the naive first-N
  warmup mis-estimates the envelope, measured at 54% false-alarm) and reports
  what fraction of damaged windows drop below it vs. the held-out healthy
  false-alarm floor. **Measured locally (--warmup 200): SB false-alarm 7.0%,
  detection 4.5–21.1% per severity (best DS5); SC false-alarm 9.9%, detection
  5.9–26.4% (best DS3).** So even a purpose-built feature-RMS detector only
  reaches ~2–2.6× its own false-alarm floor — a **weak** separation, consistent
  with the score-level CHECK (the healthy window-to-window RMS spread across
  the SM/NM + P1/P2 + Y/Z recording mix is the binding constraint, not the
  detector). A monitor is only informative if detection clearly exceeds its own
  false-alarm floor; report the rates as measured, do not tune the p5 to force
  a pass. Larger `--warmup` (e.g. 200) gives a better envelope estimate.

If either level **does** separate on the server, great — that is measured
evidence for per-structure generalization. If it does **not**, that is the
finding; report it as-is. Do not tweak thresholds to make it pass.

## 4 · Where the artifacts go / next steps

- `hbta_*_weights/{vae.pt, ocsvm.pkl, scaler.pkl, lstm_ae.pt}` + `train_meta.json`
  are ready to drop into the repo at `models/weights/` for an
  `AnomalyDetector(weights_dir=...)` per-structure evaluation (the Z24 demo arc
  is NOT touched — shipped weights stay as they are).
- The honest interpretation of the local CHECK: **the envelope-floor+push
  architecture does not generalize the anomaly RANKING to HBTA as configured** —
  its healthy envelope is built for Z24's tight healthy raw distribution. This
  is a real, actionable finding for per-structure deployment: per-structure
  retraining must either (a) refit the envelope/scaler on the target structure
  (which is what this package does) AND (b) re-evaluate whether the raw score
  ranks that structure's damage above ITS OWN healthy ceiling. The feature-level
  table exists precisely to check (b).

## 5 · Repro / honesty notes

- Deterministic: prep's damaged subsample is seeded (default seed 0); verify
  seeds torch/numpy. Healthy windows are NOT subsampled (the whole undamaged
  phase is used).
- prep emits per-window channel provenance (`healthy_ch.npy`, `damaged_ch.npy`,
  `channel_names.json`) so verify can group per sensor family instead of
  blurring SB and SC together.
- HBTA acceleration is a different physical scale than Z24 (m/s² at a
  full-scale bridge). That is the point of a per-structure retrain — the
  envelope/scaler are fit on HBTA itself, never on Z24 numbers.
- If `data/z24` is not shipped in this tar that is intentional: HBTA is
  self-contained. The Z24-trained shipped weights stay in the repo.
- Correction history: an earlier note claimed "SC strain peak_freq 3.8→7–10 Hz
  separates". That is **withdrawn** — it does not reproduce with
  `models/vibration/features.extract_features` (peak_freq = argmax PSD excluding
  DC, which for quasi-static strain sits in the low-frequency noise floor).
  The reproducible feature-level response is the RMS mean drop above.
