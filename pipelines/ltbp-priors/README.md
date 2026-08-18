# LTBP Priors — real NBI condition data → deterioration + Markov priors

Reads FHWA **InfoBridge** public exports and turns **real National Bridge
Inventory (NBI) condition data** into honest priors for a bridge twin's Markov
deterioration model — the empirical transition matrix and cross-sectional
deterioration curve behind the twin's "years to NBI ≤ 4" projection.

## What this pipeline does

| Step | Detail |
|---|---|
| **Input (raw, gitignored)** | `ltbp_pilot_44br.txt` (44 LTBP pilot bridges, **1993–2025 = real longitudinal**), `ltbp_fleet_1892br.txt` (1,892-bridge fleet **cross-section**) |
| **Empirical Markov matrix** | Year-over-year super/sub condition-state transitions computed from the **pilot bridges only** (the one real longitudinal set) |
| **Deterioration curve** | Current super/sub condition vs bridge age from the **fleet** (large N, one condition per bridge) |
| **Fleet snapshot** | Current condition / age / climate distribution |
| **Output (committed)** | `data/ltbp/analysis/ltbp_summary.json` + `ltbp_report.md` — ingested by `deterioration.py` as the Markov prior base |

## Known data quirk (verified, not hidden)

The export field named `58 - Deck Condition Rating` is **saturated** (0/1,
constant within every bridge) — it is NOT the real NBI 0–9 deck rating.
This pipeline therefore uses only super (59) and sub (60), which are genuine NBI
ratings in this export. Deck condition must come from another source.
Committed outputs are labelled within the JSON so a consumer cannot silently
misread deck data.

## Run

```bash
python ltbp_analyze.py   # needs the raw InfoBridge exports present (gitignored)
```

## Provenance & license

- **Dataset:** FHWA InfoBridge public "Selected Bridges" export, downloaded
  2026-08-14. **License: US federal open data (public domain)** — freely
  publishable, including the derived priors, with attribution to FHWA/InfoBridge.
- **Code license (this package):** MIT — see `LICENSE`. Code license does not
  replace the data license.

## Honesty note

The Markov matrix is *empirical and prior* — it is a real-inspection-informed
starting point, not a guaranteed deterioration rate for any specific bridge.
The twin labels every years-to-NBI result as a **projection under a prior**, never
as certified remaining life (Rules 1 & 4 in `../../docs/HONESTY-METHODOLOGY.md`).

## Canonical location

Maintained at `scripts/ltbp_analyze.py` (this file is a publication snapshot,
generated 2026-08-18).