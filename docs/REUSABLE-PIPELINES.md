# VITISH SHM · Reusable Pipelines & Data Licenses

**§7.6 item 19.** The pieces of this repo that are safe to extract and republish
— standalone scripts each carrying its own `LICENSE` (MIT for code) and a README
that states the *data* license separately from the code license. Codified in
[`docs/HONESTY-METHODOLOGY.md`](HONESTY-METHODOLOGY.md), Rules 5 & 7.

## How to publish a pipeline

1. Copy the canonical script into `pipelines/<name>/` (publication snapshot).
2. Add `pipelines/<name>/LICENSE` — MIT for code (full text, "Copyright (c) 2026 VITISH SHM").
3. Write `pipelines/<name>/README.md` — purpose, method, inputs, run command,
   provenance (what/how/terms), and a **data-license statement** only used the
   code license does not cover.
4. Never copy raw data files into a pipeline package. Committed artifacts are
   derived and reproducible via the documented command.

## Publishable pipeline packages

| Package | What it derives | Data source | Data license | Publish? |
|---|---|---|---|---|
| [`pipelines/z24-mirror/`](../pipelines/z24-mirror/) | Deterministic per-label window fixture from the real Z24 bridge benchmark | KU Leuven Z24 campaign (991 MB raw, gitignored; community mirror) | Public research benchmark — **cite the Z24 reference**; verify the mirror's redistribution terms before mirroring the RAW file | ✅ Derived subset published with citation |
| [`pipelines/crack-seg-converter/`](../pipelines/crack-seg-converter/) | YOLO-seg crack dataset from real crack imagery | CrackSeg9k (CC0) / Ultralytics crack-seg (verify) / SDNET2018 (registration-gated) | Per-source, see matrix below | ⚠️ **CrackSeg9k CC0 ✅ · SDNET2018 ❌ never** |
| [`pipelines/ltbp-priors/`](../pipelines/ltbp-priors/) | Empirical Markov priors + deterioration curve from real NBI data | FHWA InfoBridge public export (LTBP pilot 44 + fleet 1892) | **US federal open data (public domain)** | ✅ Yes |

## Data-license matrix (what may ship, what may not)

| Dataset | License | In public artifacts? | Source notes |
|---|---|---|---|
| **CrackSeg9k** (9,159 crack photos + masks) | CC0 | ✅ Yes — publish freely | parquet → YOLO-seg via `prep_crackseg9k.py` |
| **Z24 bridge benchmark** (vibration) | Public research benchmark (cite) | ✅ Derived fixture yes — raw 991 MB no | see `pipelines/z24-mirror/README.md` |
| **LTBP / FHWA InfoBridge** (NBI condition) | US federal open data | ✅ Yes | public domain; attribution to FHWA |
| **Ultralytics crack-seg** (~91.6 MB) | MIT code; dataset redistribution terms unverified | ⚠️ Verify before mass redistribution | local training only until verified |
| **SDNET2018** (56k+ concrete crack crops) | IEEE DataPort **registration-gated** | ❌ **Never** | ingest-only for method exploration; approximate labels generated locally, never shipped |
| **dacl10k** (10k crack images) | **CC BY-NC** (non-commercial) | ❌ **Never** | development-only; not production training data |

## Repo-root license status

The repo root has **no license file on purpose** (it is a commercial venture
repo; see the BD/methodology notes). Only the three `pipelines/*` packages carry
an explicit MIT code license. If you extract a pipeline, ship the `LICENSE` file
that already lives in its package directory.

## Enforcement

- `docs/HONESTY-METHODOLOGY.md` Rule 7 — a non-commercial or registration-gated
  dataset (dacl10k, SDNET2018) appearing in a commit inside `pipelines/` or a
  published artifact is a violation; raw files of all sources stay gitignored.
- CI (`scripts/verify_gate.sh`, gate 20) — `test_crack_width.py` and the honesty
  gate regression-assert the pixel-uncalibrated label; the pipeline licenses
  themselves are doc review (Rules 5 & 7 by reviewer, per the methodology doc).

---

Part of §7.6 item 19 · generated 2026-08-18 alongside `docs/HONESTY-METHODOLOGY.md` and the three pipeline packages.