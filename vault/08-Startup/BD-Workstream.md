---
tags: [startup, bd, roadmap, vitish-2026, pilot]
created: 2026-08-17
---

# BD & Partnership Workstream — dated owners + acceptance criteria

> COMPREHENSIVE-ANALYSIS §7.6 **item 16** — "the real critical path."
> Partners: [[Company-Project]] · [[PostHackathon-Prep]] §119–§120 ·
> [[Competitive-Landscape]] · [[Key-Decisions]].
>
> **Honesty rule for this document:** nothing claimed here may outrun what the
> repo + pilots can prove.  Every acceptance criterion is a dated, checkable
> artifact — a signed LOI, a filed incorporation, a written TAM table, a
> published calibration mapping.  A date without an owner and an acceptance is
> not a plan.

## 0. The gap this closes

The tech is built and demo-verified (arc 87.1→67.5→33.6, 18 gates, all labels
honest).  What is **not** done: no LOIs, no incorporation, no named CEO/BD, no
bottom-up TAM table, no CRN↔BHI calibration protocol.  Item 16 converts §120's
eight blocking human actions into a dated workstream so the 90-day window ends
with procurement conversations, not just a demo.

## 1. Owner & the pilot funnel

| Slot | Owner | Status | Deadline |
|---|---|---|---|
| **CEO / BD (pilot funnel + MoRTH/policy relationships)** | **OPEN — the founding gap** ([[Company-Project]] §14) | must be named or the item is stuck; the tech is not the constraint, the procurement channel is | **2026-08-31** |
| Pilot 1 — **state PWD bridge** (Gujarat's 1,800-bridge inspection backlog is the demand signal) | OPEN (reports to CEO/BD) | target | 2026-09-30 |
| Pilot 2 — **railway overbridge** | OPEN | target | 2026-10-31 |
| Pilot 3 — **one export structure** (university collaboration, e.g. a European/SE-Asian test bed) | OPEN | target | 2026-11-15 |
| **BHI calibration study lead** (IRICEN CRN 0–6) | OPEN | needs a partner bridge with a CRN rating first (see §5) | 2026-12-31 |

**Acceptance for the funnel (2–3 LOIs):** a signed, dated letter of intent per
pilot naming the partner structure and the data-license terms (commissioned, not
dacl10k/SDNET2018).  A verbal "interested" is not an LOI.  The LOI text must not
claim the demo's BHI is a certified rating — it is a projection pending the
calibration study (§5).

## 2. Incorporation + legal/IP review

| Action | Owner | Acceptance | Deadline |
|---|---|---|---|
| Choose the legal vehicle (Pvt Ltd vs LLP; the deck targets a 6-person pre-seed team) | CEO/BD + counsel | filed incorporation documents | 2026-10-15 |
| **IP review** — the algorithm (VAE+OCSVM/LSTM-AE/BHI fusion) + the honest-data-pipeline method (D1-5 manifest) + the CV model | counsel | a written IP memo; **dacl10k (CC BY-NC) + SDNET2018 (registration) explicitly excluded from any commercial claim** — production training data must be commissioned/licensed | 2026-10-15 |
| Assign the repo + firmware + tooling to the entity | counsel | assignment record | 2026-10-31 |

## 3. Bottom-up India TAM (from real counts, not a slide number)

Top-down already exists in [[Company-Project]] §5 ($3.96B global TAM 2026,
SAM ~$1.1B/yr, SOM 3,000–6,000 structures).  This is the bottom-up — sized from
the actual instrumented count, at the real price point:

| Layer | Count (real, cited) | Attach | Value/yr |
|---|---|---|---|
| **NH bridges** | ~1.7 lakh (MoRTH IBMS circular, 25 Jun 2026; survey deadline **30 Sep 2026**) | our $260/bridge/yr SaaS | **~$44M/yr** |
| **State highways + major district roads** | several Lakh more bridges (additive — exact audit tied to a state PWD pilot) | lower attach (budget-constrained) | TBD with pilot |
| **Railway over/underbridges** | Indian Railways operates ~1.5 lakh bridges (inspection-driven; rail is the Pilot-2 channel) | pilot-led | TBD with pilot |
| **Deployment/services** | per pilot | ~$980 pilot kit + condition reports | one-time |

**Usage:** the pitch's SOM is no longer a guess against a big TAM — the NH leg
alone (a serviceable subset, not the global TAM) is ~$44M/yr at list price, and
the SOM is a fraction of that.  Never present the ~1.7 lakh count as signed
revenue; it is an instrumented-universe ceiling for the NH leg.

## 4. Data-licensing + competitor depth + IBMS integration

1. **Data-licensing plan** — production data must be **commissioned** from pilot
   partners; dacl10k/SDNET2018 stay dev-only research data.  Written license
   templates are a pre-pilot artifact (owner: CEO/BD, acceptance: a clause per
   pilot, deadline 2026-09-15).
2. **Competitor pricing depth** — extends [[Competitive-Landscape]]: itemize
   what Encardio/Proqio, SPPL (IIT-D OSHMAS), Bentley/Esri charge at fleet
   scale; our wedge stays "open, dataset-driven, low-cost, 4-in-1."
3. **IBMS integration path (deadline 30 Sep 2026)** — the IRC-118 / IBMS
   condition report + inventory CSV (DONE, item 10) is the packaging; the path
   is a submission/pilot conversation with a MoRTH state wing, not a build item.
4. **Refreshed pre-seed ask** — reuse the $500k / 12-months structure with the
   pilot evidence inserted; refresh only after ≥1 LOI + the calibration design.

## 5. CRN ↔ BHI calibration-study protocol (named pilot deliverable, §119)

**Target:** for N pilot bridges that already carry an IBMS **CRN 0–6** rating
(IRICEN), regress CRN onto the BHI sub-indices and pick bands/weights by
agreement with the authority, **not by demo-arc aesthetics**.

1. **Inputs per bridge:** measured BHI sub-indices (cv / vib / load over a
   baseline window) + the official CRN 0–6 rating.
2. **Design:** ordinal regression of CRN onto the three sub-indices; report the
   fitted bands, n, and residual distribution per band.  Threshold-at-flat-floor
   honesty: if n < 8, publish as a **feasibility read, not a certified mapping**
   (mirrors the fleet-priority label on the S1 RUL surface).
3. **Arc integrity:** the demo arc (87.1/67.5/33.6) is re-pinned **only if the
   study says the demo band is wrong**; until then the regression is additive and
   never tunes thresholds to force a pass.
4. **Artifacts:** a published mapping CRN ↔ BHI with documented sample size, the
   per-band table, and a one-line verdict per band ("agrees with demo band" /
   "shifts by +/−x").
5. **Acceptance:** the mapping document exists with a dated sample size; the
   Q&A "170 vs 42" and "is the rating certified?" answers point to it.

## 6. Dependencies — what blocks this workstream

- **Nothing blocks the plan itself** (this document, owners, §3 TAM).
- **LOIs (Pilot 1–3), incorporation, and the calibration study all require a
  named CEO/BD first** — the single hard dependency.
- **Item 20 (hosted public demo / landing page) is separately gated** on the
  SEC items landing (compose loopback binding, broker auth/ACL, WS origin
  validation, Postgres port pin), so it is scheduled after those.
- The repo-side calibrations (temperature-invariant retrain, item 17;
  learning-loop v1, item 21) proceed in parallel and de-risk the pitch with
  measured evidence.

**Acceptance for item 16 as a whole:** every row above has a dated owner and a
named artifact; the bottom-up TAM exists as §3; the calibration protocol exists
as §5; and nothing in the pitch claims more than the repo + pilots can prove.

Related: [[Company-Project]] · [[PostHackathon-Prep]] · [[QandA-Prep]] ·
[[Verified-Facts]] · [[Competitive-Landscape]] · [[Key-Decisions]]