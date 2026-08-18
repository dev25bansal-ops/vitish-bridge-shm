# VITISH SHM · Honest-Findings Methodology

**Status: authoritative as of 2026-08-18 (§7.6 item 19).** This document codifies the
honesty rules every finding, number, and artifact in this project must satisfy — the
"honest-engineering posture" that is also the brand gate (`vault/08-Startup/Company-Project.md`
§14/§15). It exists so a reviewer, judge, investor, or pilot customer can verify *how* a
claim was produced, not just *what* the claim says. Where a rule is enforced by an automated
gate, the rule names the test file; where it is enforced by convention, the convention names
its own failure condition.

---

## Rule 1 — Report only what was measured; never strengthen a number

Every number in docs, tests, the pitch deck, and the demo must be as-measured or as-verified.
Nothing is rounded up, extrapolated, or "made to look better" to pass a gate.

- **Negative results are first-class.** The §7.6 item-17 decision gate is a complete `NO-FLIP`
  record: the candidate's ONE better number (label{1} confound 0.3063 → 0.0000) is reported
  exactly as measured even though the candidate was rejected (`docs/ITEM17-RETRAIN.md`).
  The HBTA per-structure retrain reproduced a ~50% strain-RMS drop yet is honestly labelled
  "weak" (SB/SC detection 3.4–17.2% vs fatigue 5.4%) in the §117 follow-up.
- **Pinning a weakness and shipping it beats hiding it.** Trained-path LEG C healthy labels
  {1} and {6} are documented *state-confounds* (max ~0.31 / ~0.37) and are pinned in the gate
  rather than tuned away or asserted away (`backend/tests/test_deconfounding.py`).
- **Failure condition:** any doc sentence that compares a shipped number to a target must also
  show the measured number; any candidate-run post-mortem that omits a countervailing result
  for the candidate is a violation.

## Rule 2 — Never move bounds to admit a candidate

Gate thresholds are fixed **before** a candidate runs. A candidate passes only by clearing the
same bounds the shipped state clears — it is never installed by loosening the target.

- The item-17 probe (`tools/probe_scale_temp.py`) measures LEG C/D bounds as declared in the
  gate; the verification runs the candidate through the **real** suite (`test_deconfounding.py`)
  with the shipped weights sha256-backed-up and restored afterward.
- **Failure condition:** any commit that edits a gate's numeric assertion to match a candidate's
  observed value, without a documented re-measurement justification, is a violation.

## Rule 3 — Every human-facing surface carries a truthful source label

Any score produced by simulation, fallback, or script pays for it with a label, always present,
never silent:

- `source` on every evidence dict: `cv_feed`, `cv_feed-fallback`, `live-cv-subindex`, `segmentation`,
  `scripted-fallback` … (`backend/app/cv_feed.py`, `models/fusion/condition.py`).
- Site temperature: `temp_source` flips `measured` ↔ `modeled` (`backend/app/site_temperature.py`);
  real T is display/provenance only and never fused into the anomaly floor or BHI.
- LIVE gating (item 15): `live` is `online AND received` — a node with firmware committed but no
  measured packet returns `live: False` + `live_label` "OFF-LINE — no measured packet yet …"
  (`backend/tests/test_honesty_gate.py`, 46 checks).
- Per-bridge telemetry labels ("never a live field sensor", "never real inspection data",
  registry `source_label`) block a simulated surface from being read as real (item 14/15).
- **Failure condition:** any new output dict that omits a source/fallback/live field while a
  sibling dict carries one is a violation (regression-tested by `test_honesty_gate.py`).

## Rule 4 — Calibration & metrology are declared, never implied

- Crack width is measured in **pixels** and always tagged `unit:"px"` + `calibrated_mm:None`
  (§7.6 item 18; `models/cv/crack_width.py`). px→mm requires a known physical scale target;
  without it the number is explicitly "uncalibrated, never certified metrology".
- The CRN↔BHI calibration study is a specified protocol, not a done mapping: n<8 ⇒ "feasibility
  read not certified mapping" (`vault/08-Startup/BD-Workstream.md`).
- The IRC-118/IBMS report generator prints mandatory "DRAFT … Not a certified assessment" on the
  PDF cover and every CSV row (`backend/app/condition_report.py`);
- "RUL / years to NBI≤4" is labeled a projection-under-a-prior on every render — never a
  certified remaining life (item 7, `lib/rulBand.ts` + `deterioration.py`).
- **Failure condition:** any new measurement pipeline that emits a number without its unit and
  calibration status is a violation.

## Rule 5 — Provenance is recorded at the source

Every derived artifact names where its data came from, when it was downloaded, and under what
terms — usually in the generating script's docstring (e.g. `scripts/ltbp_analyze.py`:
"FHWA InfoBridge public Selected-Bridges export, downloaded 2026-08-14 … License: US federal
open data"). The data-realism manifest and per-dataset pages record the same for every dataset.
Raw files stay gitignored; only derived, reproducible artifacts are committed with the command
that rebuilt them.

- **Failure condition:** a committed derived dataset/artifact without a documented origin and
  regeneration command is a violation.

## Rule 6 — Determinism and air-gap for gates; CI turns SKIP into FAIL

- The suite is deterministic and network-free: `VITISH_SITE_TEMP_DISABLE=1` forces the simulated
  temperature fallback; live paths are unit-tested with faked transports (faked HTTP client,
  fake psycopg2, byte-identical simulators).
- Under `CI=1`, a trained-ML gate that prints `TRAINED_REAL_DATA=SKIP` is a **failure** — the
  committed fixture must make it run real evidence on a fresh clone (`scripts/run_tests.sh`).
- **Failure condition:** any `SKIP` in a gate that CI cannot turn into a failure is a silent gap.

## Rule 7 — Data licensing is honored; nothing non-commercial ships

CC BY-NC (dacl10k) and registration-gated (SDNET2018) datasets are **development-only** — usable
for method exploration here, never published, never claimed as production training data, and
explicitly excluded from the public pipeline packages (§7.6 item 19, `docs/REUSABLE-PIPELINES.md`).
Publishable pipelines carry an explicit license (`pipelines/*/LICENSE`, MIT for code) and the data
license is stated separately in each pipeline README — code license ≠ data license.

## Rule 8 — The demo is a verified demonstration, labeled as such

Scripted beats are allowed but never presented as measured results; where a real path exists it
runs real evidence (real crack photo through the real YOLO, real Z24 replayed). The pinned arc
(BHI 87.1 → 67.5 → 33.6) is a *regression-pinned demonstration*, and `scripts/verify_demo_arc.py`
re-pins it against data every run (19 checks).

## Rule 9 — Open items stay openly open

Anything not built is labelled OPEN with a named next step or human owner — the CEO/BD slot
(2026-08-31), the unflashed edge boards ("no board flashed; no LIVE badge until a measured
packet"), item-17's temperature-invariant retrain (candidate failed; next experiment
documented). No silent scope-shrink.

---

### How to use this document

- **New code:** before adding an output surface, checklist Rules 3–4 (labels + units). Before
  claiming a metric, check Rules 1–2 (measured? bounds pre-set?).
- **Reviewing a diff:** the merge gate (`scripts/verify_gate.sh`) enforces the mechanical parts
  (20 gates: source labels, honesty gate, calibration, determinism). Rules 1–2 and 8–9 are
  enforced by the reviewer reading this document.
- **Publishing:** any pipeline extracted from this repo must carry its `pipelines/*/LICENSE` and a
  data-license statement — see `docs/REUSABLE-PIPELINES.md`.