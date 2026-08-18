# Z24 Window Mirror — real benchmark → per-label window fixture

Reproducibly samples a small, deterministic slice of the **real Z24 bridge
benchmark** (KU Leuven / Z24 campaign vibration data) into separate per-label
window groups, so trained-ML gates can assert healthy-vs-damaged separation on
**real** evidence everywhere — a fresh clone, CI, and the demo machine — without
committing the 991 MB raw file.

## What this pipeline does

| Step | Detail |
|---|---|
| **Input (raw, gitignored)** | `inputs.npy` (991 MB, float32) + `labels.npy` — the full Z24 benchmark |
| **Sampling** | Deterministic round-robin across the requested labels; 1024-sample (≈10.24 s @ 100 Hz) windows on channels 6/7/8 |
| **Grouping** | One `.npy` per state family: `healthy0` (label 0, the envelope's own state), `healthy1` (label 1), `label6` (label 6), `damaged` (labels 2–5, 7–16) — the grouping deliberately *keeps* the documented state-confounds visible instead of hiding them |
| **Output (committed)** | `data/z24/fixture/*.npy` — 180 windows × 1024 samples per group, ~0.74 MB each (~2.9 MB total) |
| **Consumed by** | `backend/tests/test_trained_path.py`, `backend/tests/test_deconfounding.py` LEG C, `backend/tests/_z24_data.py` |

## Reproduce / regenerate

```bash
# needs the full real file present:
python scripts/make_z24_fixture.py --n-seg 12
```

> The **committed fixture is the shipped evidence**. A regenerated fixture is a
> different (still-real) sample, so the gates' separation bounds MUST be
> re-measured on it before use.

## Data provenance & license

- **Dataset:** Z24 bridge benchmark — real forced-vibration + ambient data from
  the 1996–1998 Z24 campaign (a 58 m, three-span prestressed concrete bridge in
  Koppigen, Switzerland, progressively damaged then monitored).
  Cite the Z24 reference when you publish results from it.
- **License:** public research benchmark; the full 991 MB raw file is obtained
  from a community mirror — **verify the mirror's redistribution terms before
  mirroring or republishing the RAW file**. The small derived fixture here is
  published with the benchmark citation (a derived, non-competing subset).
- **Code license (this package):** MIT — see `LICENSE`. Code license does not
  replace the data license.

## Honesty notes (why the grouping matters)

The per-label grouping exists so a gate cannot "pass" by averaging healthy
every-state confusion into one blob: label {0} is asserted quiet (envelope's own
state), labels {1} and {6} are **pinned documented confounds** (max ≈0.31/0.37,
not hidden), and only the damaged mean is required to separate (≥0.05). This is
§7.6 item 19 / Rule 5 & Rule 1 in `../../docs/HONESTY-METHODOLOGY.md`.

## Canonical location

Maintained at `scripts/make_z24_fixture.py` (this file is a publication
snapshot of that script, generated 2026-08-18).