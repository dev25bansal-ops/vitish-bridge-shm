# Workstreams — 3-person parallel build

> Everything below flows from the digital-twin realism roadmap in
> `vault/02-Research/Realistic-Digital-Twin.md`. **Read that note + `vault/Home.md`
> first.**
>
> **Non-negotiable:** the demo arc GREEN 87 → AMBER 67.5 → RED 33.6 must NEVER
> break. Stream C task C1 (pin the arc as a regression test) lands FIRST and is the
> merge gate for every other stream.

## Repo layout (for teammates)

| Path | What it is |
|---|---|
| `backend/` | FastAPI pipeline + WS bridge (port 8000 / 8765) |
| `twin/` | React 19 + R3F three.js digital twin (Vite, port 5173) |
| `models/` | Vibration (`vibration/`), CV (`cv/`), fusion/BHI (`fusion/`) |
| `data/` | Real datasets (gitignored, re-downloadable): `z24/`, `vib/`, `cv/`, `ltbp/` |
| `scripts/` | Data + analysis scripts (e.g. `ltbp_analyze.py`, `download_dacl10k.py`) |
| `vault/` | Obsidian research/build notes (single source of truth) |
| `docs/` | This + architecture docs |

**Data you need but is gitignored:** `data/z24/inputs.npy` (991 MB Z24 replay),
`data/ltbp/*.txt` (re-download from FHWA InfoBridge or ask for a copy), CV datasets.
`models/weights/*.pt` are trained artifacts — re-train or ask.

## Branch + PR workflow

- One long-lived branch per stream: `stream-a-model`, `stream-b-twin`, `stream-c-integration`.
- Work on your branch → open a PR to `main`. Never push straight to `main`.
- The demo-arc regression test (C1) runs in CI/gate before merge.

---

## Stream A — Models & Data (Python backend)

**Owner:** person who owns `backend/` + `models/`.

| # | Task | Files | Roadmap |
|---|---|---|---|
| A1 | **Wire LTBP Markov priors into the deterioration model** — read `data/ltbp/analysis/ltbp_summary.json`, replace hardcoded literature priors with empirical ones (label "empirical LTBP prior, small n"), keep it honest | `backend/`, `models/fusion/` | #8 |
| A2 | **Temperature normalization of vibration signature** — synth T channel, regress f1 vs T, residual-drift overlay (Z24 lesson: ~14% seasonal shift from temp alone) | `models/vibration/`, `backend/` | #4 |
| A3 | **Per-channel synthetic sensor models + data-realism manifest** — noise/drift/spikes/ADC on *synthetic* channels only; never corrupt the real Z24 replay; manifest lists σ/rate/filter per channel | `backend/`, `models/` | #5 |
| A4 | **Resume U-Net crack training** (parked, GPU-contended) → real `crack_unet.pt`; keep CrackSeg9k/negative prep + verify scripts working | `models/cv/` | — |
| A5 | **Event-triggered capture + replay** (Honshu-Shikoku pattern) — low-rate background, high-rate capture + incident record on threshold trip, replayable | `backend/` | #11 |

---

## Stream B — Twin Frontend (TypeScript / React / three.js)

**Owner:** person who owns `twin/src/`.

| # | Task | Files | Roadmap |
|---|---|---|---|
| B1 | **Cesium georeferenced layer** — token already in local `twin/.env` (`VITE_CESIUM_TOKEN`); add Cesium, terrain + Google Photorealistic 3D Tiles, wire into the scene so the bridge isn't floating in a void | `twin/src/`, `twin/package.json` | #10 |
| B2 | **Simulated clock + time-lapse label** ("simulated day 214/365, clock ×1800") — visible everywhere a temporal claim is made | `twin/src/panels/`, `twin/src/scene/` | #3 |
| B3 | **Digital-shadow label + provenance UI** — "digital shadow, one-way data", data-realism manifest viewer, which channels are measured vs modeled | `twin/src/panels/HealthPanel.tsx` | #1 |
| B4 | **Visualization realism bundle** — heatmaps with physical-unit legends, labeled deflection exaggeration (×5000), stale-sensor glyphs (GREY), uncertainty bands on trends | `twin/src/scene/`, `twin/src/panels/` | #10 |
| B5 | **Component asset registry (frontend)** — raycast detail cards: spec/history/next-inspection/photo links keyed to 3D component IDs | `twin/src/scene/SensorPopup.tsx` etc. | #13 |

---

## Stream C — Integration & Story (full-stack, demo owner)

**Owner:** the person who runs the demo end-to-end. Does C1 FIRST.

| # | Task | Files | Roadmap |
|---|---|---|---|
| C1 | **PIN THE DEMO ARC as a regression test** — assert 87 → 67.5 → 33.6 (with tolerances) so no stream change silently breaks the story | `backend/`, `models/`, `scripts/` | #2 |
| C2 | **Bridge-identity decision + stiffness-from-frequency proxy** — DECISION NEEDED (see below): either 30 m box girder (match Z24 physics) or keep cable-stayed (harder frame FE). Then `EI = 4·f1²·L⁴·ρA/π²` drift overlay + mode-shape animation | `models/vibration/`, `twin/src/scene/` | #7 |
| C3 | **Regulator condition card from the real crack index** — map segmentation → relative severity → condition state (post-Morandi risk class / NBI with explicit confidence); never a raw CV score | `backend/`, `models/fusion/`, `twin/src/panels/` | #6 |
| C4 | **Markov + Bayesian updating (UI wiring)** — condition curve moves with each measured crack state; next-inspection trigger; uncertainty fan; consume Stream A's priors | `twin/src/panels/HealthPanel.tsx`, `backend/` | #8 |
| C5 | **Seeded-defect demo grounded in Z24/S101** — damage scenario reduces per-span EI N% → f1 shifts per Z24/S101 evidence; arc stays as guardrail | `backend/`, `models/vibration/` | #12 |
| C6 | **Crack severity → image-to-3D photo registration** — skeleton + distance transform → width/area; register detections to components | `models/cv/`, `backend/`, `twin/src/scene/` | #14 |
| C7 | **Component asset registry (data model)** — JSON asset model keyed to 3D component IDs + sensor schema; feeds B5 | `backend/` | #13 |

---

## Open decisions that block streams

1. **Bridge identity (blocks C2, affects B1/B5):** current mismatch — `contract.py` says
   `bridge_id="z24"` (30 m box girder) but the 3D mesh is a 230 m cable-stayed deck.
   Pick ONE. Cheapest honest option: adopt the 30 m box-girder mesh to match Z24 physics.
2. **Z24 full dataset (blocks A2/A5 grounding):** registration-gated at KU Leuven
   (`bwk.kuleuven.be/bwm/z24`). Until it arrives, use the existing `data/z24/inputs.npy`
   replay + synthesized temperature.
3. **Cesium token** lives only in the local `twin/.env` — teammates copy it from the owner,
   never from the repo.

## Definition of done

- The demo arc regression test (C1) passes on `main` after every merge.
- Every on-screen number traces to a repo dataset or a clearly-labeled model assumption.
- No claims added to the "claims we will not make" list (see Realistic-Digital-Twin §3).
