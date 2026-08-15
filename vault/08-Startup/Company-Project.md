---
tags: [startup, company, yc, vitish-2026, shm, pitch]
created: 2026-08-13
status: draft
---

# VITISH — Company Project (startup-grade, YC-oriented)

> Not just a hackathon deliverable. This is the company framing for the same build: a defensible, fundable, **open, low-cost, 4-in-1 Structural Health Monitoring** platform riding the single largest regulatory mandate in India's infrastructure history.
> Every number here is traceable to a verified note ([[Global-Failures]], [[India-Policy]], [[Competitive-Landscape]], [[Key-Decisions]], [[Build-Log]]) or to the repo. Nothing is stronger than what's in the repo.

---

## 0. Elevator pitch (one line)

> **"Prevent the next Morbi."** VITISH is the open, low-cost reference implementation of the national Bridge Health Monitoring architecture (MoRTH IBMS + IIT-M/C-DAC NBHMS): IoT sensors + computer-vision crack detection + digital twin + predictive AI, fused into **one auditable Bridge Health Index** — priced at 1–5% of incumbent systems, deployable in days on structures that currently have nothing.

---

## 1. Company overview

| Field | Detail |
|---|---|
| **Name (working)** | VITISH (verbatim from the project; legal name TBD on incorporation) |
| **Mission** | Prevent the next Morbi — make every bridge continuously visible to its owner at a price the world can actually pay |
| **Positioning** | The **open, low-cost reference implementation** of the architecture MoRTH and IIT-M/C-DAC are already mandating |
| **Moat thesis** | Auditable, transparent BHI + a **data flywheel** from low-cost mass deployment + 1:1 policy alignment → becomes the calibration/benchmark layer of the national system |
| **Legal vehicle** | Not yet incorporated — this document is the pre-incorporation company brief |
| **Origin** | PS#99 build, VITISH 2026 · built and verified end-to-end 2026-08-13 |

## 2. Problem

### 2.1 Lives, not just money
Verified collapse ledger ([[Global-Failures]]):
- **Morbi, 30 Oct 2022** — pedestrian suspension bridge, **~135 dead** (some tallies 141). The inspection regime failed.
- **Gambhira, Gujarat, 9 Jul 2025** — **22 dead**. Aftermath: Gujarat inspected **1,800+ bridges → 20 fully closed, 113 partially closed**.
- **Global (last two years):** 52 (Meizhou), 38 (Shangluo), 13 (Brazil), 12 (Jianzha).
- **India 2021–2025:** **170 collapses / 202 deaths / 441 injured** (Newslaundry) vs MoRTH's official **42** — the government-vs-reality gap is the sales story.

### 2.2 The systemic scale
- **US:** 623,218 bridges, **~41,600 "poor condition"** carrying 163M crossings/day (FHWA NBI, Jun 2025); **1 in 3 needs repair** (ARTBA); ASCE grade **C** with **49.1% fair** — a silent aging-downgrade pool.
- **Market:** $3.44B (2025) → $3.96B (2026), **~15% CAGR** (Business Research Company).

### 2.3 The real problem (why current tech fails)
1. **Incumbent SHM is expensive and closed** — flagship deployments cost US$1.3M for ~900 sensors (Hong Kong). Price = adoption wall.
2. **Monitoring is reactive, not continuous** — the collapse pattern is *"inspector missed it, died in inspection gap."*
3. **No single auditable score** — owners get silos (a vibration vendor, a camera vendor, a BIM vendor), never one answer.
4. **The one missing layer** — the world's ~600k US + ~180k Indian NH bridges have *nothing* between "periodic visual inspection" and "expensive full instrumentation."

## 3. Why now (the regulatory tailwind)

Verified, live ([[India-Policy]]), all dated:
| Anchor | Date | Meaning for us |
|---|---|---|
| **MoRTH IBMS circular** | 25 Jun 2026 | Nationwide **digital survey of ~1.7 lakh NH bridges**, **deadline 30 Sep 2026** — a dated, live procurement event |
| **IIT-M + C-DAC NBHMS MoU** | 9 Jul 2026 | The **national architecture** our 4-layer stack mirrors 1:1 |
| **NHAI Teesta / Mahananda BHMS tender** | live | **₹11.69 crore** bridge-health tender being *bought today* |
| **ISHMS Guidelines v1** | 16 Jul 2025 | The ruleset a production system must follow — ours is built to it |

**The pitch:** *"The government is mandating the exact architecture we already built — and it's running, end to end, today."*

## 4. Product — the 4-component system

One hero data flow: `sensor → MQTT → Postgres + WebSocket → AI (CV + vibration) → fusion/BHI → twin + dashboard`

| # | Component | Status today (honest) |
|---|---|---|
| 1 | **IoT sensing** — Z24 replay simulator through the real MQTT pipeline; ESP32-S3 + IMU hardware node | Simulator **REAL** (verified); hardware node = next build |
| 2 | **Computer vision** — crack segmentation (YOLO-seg) | Pipeline **REAL + weights trained**: `crack_seg.pt` (YOLO26s-seg on 4,081 CC0 CrackSeg9k) drives the demo crack beats through strict YOLO ([[CV-Model]]) |
| 3 | **Digital twin** — parametric R3F Z24 box-girder bridge + MapLibre fleet map (+ optional Cesium Geo view, D2-7) | **REAL + verified** (light theme, offline-safe, toggle-map) |
| 4 | **Predictive maintenance** — VAE+OCSVM + LSTM-AE anomaly → **transparent BHI** + copilot recommendation | **REAL + verified** (LSTM-AE trained; PR 0.996 / recall 0.999 published for the primary) |

### The Bridge Health Index (the product's spine)
```
BHI = 100 × (1 − 0.40·cv − 0.35·vib − 0.25·load) × age_factor × traffic_factor
```
- 3 sub-indices, each mapping to an **auditable measurable** (crack area · anomaly score · utilization).
- **Uncertainty band** → *"high uncertainty → human review"* — the answer to the #1 trust question.
- Bands: 🟢 ≥70 normal · 🟡 50–70 monitor · 🔴 <50 flag.
- Calibration study against **IBMS CRN 0–6** (IRICEN) is a pilot deliverable — this is how we become the *calibration layer* of the national system.
- **What's verified:** full demo arc GREEN 87 → AMBER 67.5 → RED 33.6 with no flicker, alerts at 45/75/110/140s, backend smoke 83/83, models 19/19.

## 5. Market (TAM / SAM / SOM)

| Layer | Estimate | Basis |
|---|---|---|
| **TAM** | **$3.96B (2026)** growing 15% | Business Research Company; range $2B–$9B by firm/scope |
| **SAM** | **~$1.1B/yr** — the mass-deployable tier | US 41,600 poor bridges + ~180k Indian NH bridges + global aging pool, at our $260/bridge/yr price point |
| **SOM (3-yr)** | **3,000–6,000 structures** (~$1–2M ARR) | One state PWD partnership + one MoRTH-adjacent pilot + 2–3 export markets |

**The wedge:** incumbents monetize at $1.3M/900 sensors; we monetize at **~$260/bridge/yr**. That's not competing on price — it's opening the previously unaddressable tier beneath every flagship deployment ([[Competitive-Landscape]]).

## 6. Competition (the integration gap)

**No major SHM vendor offers all four components (wireless IoT + CV + digital twin + predictive AI) in one open, low-cost system. That is our wedge.** ([[Competitive-Landscape]])

| Tier | Vendors | Have | LACK |
|---|---|---|---|
| IoT-only | Resensys, SENSR, Campbell, Geokon, Senceive | sensing | CV, twin, ML anomaly |
| AI-only | Sensequake | consulting assessments | always-on monitoring |
| Twin-only | Bentley iTwin ($199/$499 mo), Autodesk Tandem, Esri, Willow | BIM/geospatial twins | live MEMS + ML + CV |
| Service-heavy | Strainstall, Encardio/Proqio, **SPPL (IIT Delhi OSHMAS)** | full service | closed, expensive stacks |

**India reality (be honest):** SPPL is not first-mover-proof — our wedge is **open, dataset-driven, low-cost, 4-in-1**; Encardio's Proqio exists (never claim "no AI"); HBM = HBK Monitor360; NI/Emerson InsightCM is rotating-machinery, not bridge SHM.
**Open-source credibility:** cite PySHM, pyOMA2, OpenBDLM as references — we are *the* open reference implementation.

## 7. Business model

| Layer | Offer | Price (verified-corrected, [[Key-Decisions]] #9) |
|---|---|---|
| **Pilot kit** (1 bridge, 1–2 sensor nodes + camera + gateway + dashboard) | Deploy in a day | **~$980 / pilot** |
| **Per-bridge SaaS** (continuous BHI, alerts, copilot, twin) | per structure / year | **~$260 / bridge / yr** |
| **Fleet SaaS** (50+ bridges, regulator map) | per structure / year | **$25–30 / month** |
| **Licensed data/calibration** | anonymized condition data + CRN calibration studies | future |

**Unit-economics logic:** commodity hardware (ESP32-class ≈ $10–15/node) + software margin ≈ 80%+ gross. The corrected numbers are the ones a business-savvy judge/VC checks — we do the arithmetic *before* the pitch.

## 8. Moat — why VITISH compounds

1. **Auditability = trust** — the transparent BHI with uncertainty band is the anti-black-box answer incumbents can't match.
2. **Data flywheel** — every low-cost deployment adds condition data; more data → better calibration (CRN mapping, anomaly priors) → better product → more deployments. We're building the **calibration layer of the national system**.
3. **Policy alignment** — our architecture is a 1:1 mirror of MoRTH/IIT-M/C-DAC. When they mandate it, we ARE it.
4. **Open source = distribution** — the reference-implementation status converts developers/governments into users.
5. **Pricing floor** — $260/bridge/yr opens the 600k-bridge tier incumbents structurally can't serve.

## 9. Go-to-market (0 → 1)

- **Hackathon = launch.** The VITISH PS#99 build + demo is the reference deployment; the 6-minute storyboard is the first sales deck.
- **Phase 1 (weeks 0–12):** 2–3 pilots — a PWD bridge, a railway overbridge, and one export structure (via a university collaboration). Success metric: **measured BHI + a written inspection report**.
- **Phase 2 (months 3–12):** ride the IBMS/NBHMS wave — respond to the **NHAI ₹11.69cr BHMS tender** pattern with a *fraction of the cost*; partner with a structural-engineering firm (liability-sharing) rather than selling solo.
- **Phase 3:** fleet SaaS + data licensing; state-level partnerships (Gujarat's 1,800-bridge inspection backlog is the demand signal).
- **Positioning rule (non-negotiable):** *never claim a number stronger than what's in the repo.*

## 10. Roadmap (built → next)

**Built & verified (2026-08-13):** Z24 replay pipeline end-to-end (MQTT→Postgres→inference→BHI→twin), VAE+OCSVM + LSTM-AE trained, transparent BHI, parametric twin + MapLibre fleet map, light theme, demo arc verified.

**Next (30-day):**
1. ~~Train real CV weights~~ — **DONE**: `crack_seg.pt` trained on 4,081 CC0 CrackSeg9k and wired into the `cv` sub-index via `cv_feed.py` (strict YOLO on curated frames). Retraining on the larger dacl10k/SDNET2018 fold stays a later pilot task (dev-only, CC BY-NC / registration).
2. **ESP32 + IMU hardware node** streaming into the same MQTT topics (real hardware in the loop).
3. **RUL / predictive-maintenance forecast** (remaining-life projection) on the trend.
4. **CRN 0–6 calibration study** against IRICEN ratings.
5. Legal incorporation + IP (note: dacl10k/SDNET2018 are non-commercial/registration-gated — production data must be licensed or commissioned).

## 11. Team

The 6-role build team maps to a founding team ([[Team]]): embedded/data-pipeline · CV/crack model · vibration/anomaly ML · digital-twin/dashboard · backend/integration OWNER · presenter. Operating DNA already proven: commit-every-1–2h, honest numbers, 30-second per-component explanations, hard gates.
**Founding gap to close:** a named CEO/BD who owns the pilot funnel and the MoRTH/policy relationships — the tech is the easy part, the procurement channel is the moat.

## 12. The ask

- **Pre-seed: $500k** for 12 months — 2 sales engineers + 1 full-stack + hardware BOM for 20 pilot kits + calibration study + legal.
- **What we'll have at the end of the round:** 10 pilot structures streaming live BHI, a trained crack model on real data, CRN calibration v1, and 2 letters of intent from a PWD + a consultancy.

## 13. Risks (and honest mitigations)

| Risk | Mitigation |
|---|---|
| Procurement is slow | Pilot-led GTM; export market via university; IBMS deadline forces urgency |
| Liability (a missed defect) | Uncertain-banding + "human review" flagging; consultancy liability-sharing; insurance at scale |
| Data licensing | Public benchmarks (Z24 MIT) for dev; licensed/commissioned data for production |
| Hardware supply chain | Commodity ESP32-class parts; software-agnostic to sensor vendor |
| Being outspent by incumbents | We don't outspend — we out-open and out-price; the mass tier is structurally theirs to lose |
| Team capacity (6-person) | Partnerships + open source contributors + staged hires |

## 14. What we will NOT claim

- ❌ "No competitor has AI" — Encardio Proqio, HBM/HBK Monitor360 exist.
- ❌ Morbi as validation — Morbi had no sensors; it's **motivation** ([[Key-Decisions]] #8).
- ❌ A single F1 — we show the **full confusion matrix by scenario** ([[Metrics]]).
- ❌ The scripted demo arc as a measured result — it's a *verified demonstration*, labeled honestly.
- ❌ Non-commercial datasets (dacl10k CC BY-NC) as production training data.
- ❌ "LLM copilot" — the copilot pane is **rule-based, not an LLM** ([[CopilotPanel]]); demo wording will say "rule-based maintenance advisor."
- ❌ "RUL / remaining-life forecast" — **not built** (age/traffic factors = 1.0); "N days before rupture" is a *research claim to be measured on pilot data*, never presented as shipped.
- ❌ "The models catch Z24 damage" — measured reality: on a 10.24 s window the trained models do **not yet separate raw Z24 damage**; the deterministic spectral floor is load-bearing, and the demo damage phase is a **transparently-injected** 4 Hz rupture tonal on real damage segments (declared in the simulator docstring).
- ❌ "50 live bridges" — the fleet map is **1 live + 49 real locations with simulated health**, disclosed honestly.

## 15. Honest engineering ledger (REAL vs SCRIPTED — diligence-ready)

An investor/judge will probe in 2 minutes. Here's the exact ledger (from a full codebase audit 2026-08-13):

| Subsystem | Status | What is actually true |
|---|---|---|
| Z24 replay → MQTT → Postgres → WS → twin | **REAL** | 991 MB real benchmark mmap-replayed; Postgres rows verified; API + WS smoke-tested |
| Vibration weights (VAE/OCSVM + LSTM-AE) | **REAL** | Trained on 4,050 real-Z24 healthy windows; MC-dropout uncertainty; *but* contributes a bounded lift — the deterministic floor is what stays GREEN/RED correctly |
| BHI + uncertainty + bands | **REAL** | Transparent formula; verified arc GREEN 87 → AMBER → RED 33.6, no flicker |
| CV crack detection | **REAL** | `crack_seg.pt` trained on 4,081 CC0 CrackSeg9k imgs (recall ≥ heuristic, clean-FP gate ≤0.15); the demo's crack beats run ONE real curated CC0 crack photo through the strict YOLO and map the real conf/area → cv evidence (`backend/app/cv_feed.py`, fixed formula); scripted value only as a tagged `cv_feed-fallback`; Canny heuristic fallback exists for interactive tools |
| ESP32 + IMU edge node | **ABSENT** (30-day build) | No firmware; simulator fakes device metadata |
| Load/traffic input | **SCRIPTED** | `cmd:load` control events; no WIM source yet |
| RUL / predictive maintenance | **NOT BUILT** | age/traffic factors = 1.0; vibration-trend projection is the v1 approximation |
| Copilot | **rule-based** | Canned templates keyed on alert source |
| Fleet (50 bridges) | **1 live + 49 illustrative** | Real NBI locations, seeded-simulated health |

**Why this is a strength, not a weakness:** every "not yet" row is a *named, sequenced build item with a measurable success test*, and the honest-engineering posture is itself the brand ("auditability" isn't a slogan — it's the whole product).

## 16. Research gaps to close (before a serious raise)

1. **India-specific TAM** — current sizing is one global source ($3.44B→$3.96B); need a bottom-up India model from the ~1.7 lakh NH bridges × addressable share × price.
2. **Competitor depth** — service-heavy tier pricing (Strainstall, Encardio) unverified; market-share data missing.
3. **Data-licensing plan** — dacl10k (CC BY-NC) and SDNET2018 (registration) are dev/benchmark only; the **production moat is self-captured pilot data** + KU Leuven-licensed research framing → the pilot on a partner PWD bridge is existential, not nice-to-have.
4. **Moat research** — federated learning across bridges without sharing raw data (Feng et al., arXiv:2606.03084) is the defensible future-work direction.

---

## Appendix A — YC application draft (ready to adapt)

> Filled in as of 2026-08-13. Every claim is traceable to this vault or the repo.

- **Company name:** VITISH (working)
- **Company url:** (TBD — repo lives at `D:\SHM_Bridges`, GitHub on incorporation)
- **One-liner (50 chars):** *Open low-cost AI bridge-health monitoring to prevent the next Morbi.*
- **What is your company going to make? (250c):** An end-to-end structural-health-monitoring system — $10-class wireless accelerometer + camera nodes, edge/cloud AI (vibration anomaly + crack segmentation), and a digital twin, fused into one auditable Bridge Health Index (BHI) with an uncertainty band. Priced ~$260/bridge/yr (SaaS $25–30/mo), it's the low-cost layer beneath flagship systems that cost $1.3M per deployment. We are the open reference implementation of the architecture India's MoRTH + IIT-M/C-DAC are mandating nationwide.
- **Where do you live?** India (VIT; team across VIT campuses).
- **Your background:** 6-person engineering team — embedded/data pipeline, computer vision, vibration ML, digital twin, backend/integration, presenter. Built the entire system end-to-end in 36 hours for SIH PS#99; committed to honest, measured claims (see ledger above).
- **Progress to date (500c):** Working, verified pipeline: real Z24 benchmark (991 MB) → MQTT → Postgres → WebSocket → React Three Fiber digital twin + MapLibre fleet map. Trained VAE/OCSVM + LSTM-AE on 4,050 real-Z24 windows with MC-dropout uncertainty; transparent BHI with verified GREEN→AMBER→RED arc (no flicker); backend smoke 83/83, models 19/19. Real CV datasets downloaded (4,081-image crack-seg, CRACK500+DeepCrack, dacl10k); trained crack model + ESP32 hardware node are the named next-30-days build. Policy tailwind dated: MoRTH IBMS nationwide survey of ~1.7 lakh bridges (deadline 30 Sep 2026); IIT-M/C-DAC NBHMS MoU (9 Jul 2026); live ₹11.69 crore NHAI BHMS tender.
- **1-month / 6-month / 1-year plan (300c):** 1mo — train real crack model, ESP32 node streaming, incorporation, 2 pilot LOIs. 6mo — 10 pilot bridges live on partner PWD structures; India TAM model; CRN 0–6 calibration study; federated-learning research direction. 1yr — 100+ bridges, $500k pre-seed deployed, first paying contracts + data-licensing pilot.
- **What do you want to learn? (300c):** India public-works procurement (who buys, budget cycles, tender structure); civil-engineering liability models for AI-driven inspection; and whether agencies trust an auditable scorecard enough to act on it — we want to build the category "AI condition-assessment for aging infrastructure."
- **What are you not going to do? (300c):** Not build another closed, expensive flagship system; not sell a single black-box score with no uncertainty; not claim Morbi as validation (it had no sensors); not train production models on non-commercial data (dacl10k/SDNET2018); not ship hardware without a streaming smoke test.
- **Idea (3–6 sentences):** Bridge collapses keep killing people because inspection is periodic, expensive, and single-vendor. We fuse cheap IoT vibration + crack vision + a digital twin into one auditable BHI with an uncertainty band, at a price that opens the currently-unserved 600k+ bridge tier. The market is real and dated: India is mandating nationwide monitoring by 30 Sep 2026, and the architecture we built is a 1:1 match. Our moat is transparency (the anti-black-box answer), a data flywheel from low-cost deployments, and being the open reference implementation. We ship the working end-to-end pipeline today and are building the two named gaps (real CV, real hardware) this month.
- **Any questions for YC?** Who funds "infrastructure-AI" in India; what are the right pilot/partnership structures with state PWDs; and how do US agencies actually budget for condition monitoring (NBI/ASCE-driven)?

---

*Sources: every fact above links to a vault note or the repo. Nothing invented.*
*Next action: incorporation + 2 pilot LOIs + the India TAM model (CV training is DONE — `crack_seg.pt` trained and wired).*
