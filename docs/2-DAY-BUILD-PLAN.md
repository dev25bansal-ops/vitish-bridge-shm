# 2-Day Build Plan — digital twin realism (you + Claude)

> **When:** 2026-08-14 → 2026-08-16 (2 days). **Team:** 2 (you + Claude).
> **Contract:** the demo arc GREEN 87 → AMBER 67.5 → RED 33.6 must NEVER break.
> Every number on screen traces to a repo dataset or a clearly-labeled model assumption.
> Full roadmap + rationale: `vault/02-Research/Realistic-Digital-Twin.md`.

## Division of labor

- **Claude** does the building (backend, models, frontend, tests) end-to-end.
- **You** make the calls that need a human + verify the twin in the browser:
  1. **Bridge identity** (decide by end of Day 1 — blocks the physics item)
  2. Run the twin / look at the 3D scene, sanity-check visuals
  3. Handle anything behind your account: Z24 registration, GPU time for U-Net
     (quantum job must finish first), pushing branches / opening PRs
  4. Approve scope cuts if we run long (default: cut realism *polish*, never the arc)

## Non-negotiables (regardless of how long we run)

- Pin the arc test FIRST (protects every later change).
- No claiming numbers stronger than the repo (no validated RUL, no Paris-law forecast).
- Cesium token stays in gitignored `twin/.env` — never committed.
- If Z24 full package hasn't arrived, use the 991 MB replay + synthesized temperature.

---

## Day 1 — "Honest + real data" (protect the story, make the numbers real)

### D1-AM — Foundations
| # | Task | Deliverable | Files |
|---|---|---|---|
| 1 | **Pin the demo arc as a regression test** | `scripts/` test asserting 87 → 67.5 → 33.6 (tolerances), runs on every change | `backend/`, `models/`, `scripts/` |
| 2 | **Bridge-identity decision** | YOU decide: 30 m box girder (match Z24) vs keep cable-stayed. Claude implements | `contract.py`, `twin/src/scene/` |
| 3 | **Regulator condition card from crack index** | segmentation → relative severity → condition state (post-Morandi risk class / NBI w/ confidence), never a raw CV score | `models/fusion/`, `backend/`, `twin/src/panels/` |

### D1-PM — Real data + provenance
| # | Task | Deliverable | Files |
|---|---|---|---|
| 4 | **Wire LTBP Markov priors into the deterioration model** | `ltbp_summary.json` → real transition probabilities (labeled "empirical LTBP prior, small n") | `backend/`, `models/fusion/` |
| 5 | **Data-realism manifest + per-channel synthetic models** | σ/rate/filter per channel; noise/drift/spikes/ADC on *synthetic* channels only; manifest endpoint the UI can read | `backend/`, `models/` |
| 6 | **Digital-shadow label + provenance UI** | "digital shadow, one-way data" label + manifest viewer (measured vs modeled) | `twin/src/panels/` |

**Day-1 gate:** arc regression passes; mark in `vault/Build-Log.md`.

---

## Day 2 — "Look real + behave real" (georeferenced + physics)

### D2-AM — Visual realism
| # | Task | Deliverable | Files |
|---|---|---|---|
| 7 | **Cesium georeferenced layer** | terrain + Google Photorealistic 3D Tiles under the bridge (token in `twin/.env`) | `twin/`, `twin/package.json` |
| 8 | **Simulated clock / time-lapse label** | "simulated day 214/365, ×1800" on every temporal claim | `twin/src/scene/`, `twin/src/panels/` |
| 9 | **Visualization realism bundle** | heatmaps w/ physical-unit legends, labeled deflection exaggeration, stale-sensor glyphs (GREY), uncertainty bands | `twin/src/scene/`, `twin/src/panels/` |

### D2-PM — Physics + story
| # | Task | Deliverable | Files |
|---|---|---|---|
| 10 | **Temperature normalization of vibration** | synth T, regress f1 vs T, residual-drift overlay (Z24: ~14% seasonal shift) | `models/vibration/`, `backend/` |
| 11 | **Markov + Bayesian updating UI** | condition curve moves with each measured crack state; next-inspection trigger; uncertainty fan | `twin/src/panels/`, `backend/` |
| 12 | **Seeded-defect demo grounded in Z24/S101** | damage scenario reduces per-span EI N% → f1 shifts per evidence; arc stays as guardrail | `backend/`, `models/vibration/` |

**Day-2 gate:** full smoke test + arc regression + 6-minute demo dry-run end-to-end.

---

## Stretch (only if ahead of schedule)
- Event-triggered capture + replay (#11 in roadmap)
- Component asset registry + raycast detail cards (#13)
- Crack severity → image-to-3D photo registration (#14)
- Resume U-Net `crack_unet.pt` training when GPU is free, wire real inference

## Priority order if we must cut
Never cut: 1 (arc pin), 4 (real priors), 7 (Cesium), 10 (temp normalization).
Cut first: polish-only visual extras, then #11/#13/#14 stretch items.
