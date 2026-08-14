---
tags: [vitish-2026, shm, digital-twin, data-access, research]
---

# Data & Access Checklist — what to fetch, how, and what it unlocks

> Companion to [[Realistic-Digital-Twin]]. The roadmap's day-scale work needs real data and tooling that sit behind **registration, accounts, or paywalls**. This is the fetch-list: link → who needs to do what → what it unlocks in the build. **No passwords in chat** — register yourself, then either drop the data files in the repo or put tokens in `.env` (never commit them).
>
> ✅ = already in the repo · 🔐 = needs registration/credential · 💰 = paywalled paper · 🌐 = open, just download

---

## Tier 1 — get these NOW (core to roadmap items 4, 6, 12)

### 🔐 1. Z24 benchmark full dataset — KU Leuven (the #1 get)
- **Link:** https://bwk.kuleuven.be/bwm/z24 → click **"Registration form"**, then **"Obtain data"**
- **What it is:** the canonical real-damage bridge dataset — long-term accelerometer + **48 environmental (temperature) sensors** + 291-DOF modal grid + **progressive damage scenarios** (pier settlement 20–95 mm, concrete spalling, hinge failure, tendon rupture)
- **Access terms:** non-commercial research only; must acknowledge + cite KU Leuven Structural Mechanics; **data may not be transferred to third parties**
- **What to do:** one person fills the form; data arrives by email; drop the files into `data/z24/` (an empty `data/z24/` already exists next to the 991 MB `inputs.npy` replay)
- **Unlocks:** roadmap **#4 temperature normalization** (the ~14% seasonal modal shift lesson), **#12 seeded-defect demo** grounded in real damage numbers, and a real OMA pipeline test. This is the single highest-leverage dataset for making vib honest.

### 🔐 2. S101 bridge results portal — svibs.com (ARTeMIS-SHM)
- **Link:** https://www.svibs.com/cases/artemis-shm-for-structural-health-monitoring-of-the-s101-highway-bridges-austria/
- **What it is:** a demo login to the **ARTeMIS-SHM** web portal of the S101 bridge (Austria): 15 triaxial accelerometers, 714 datasets, tracked natural frequencies, damage indicators, Hotelling-T² control charts
- **What to do:** email **svibs@svibs.com** → "request the S101 bridge demo login". No public download; access is via the portal
- **Unlocks:** a reference against which to sanity-check our own frequency-tracking + anomaly output (roadmap #4/#7); real control-chart conventions for the HealthPanel

### 💰 3. Tamar Bridge cointegration paper — Cross et al., 2013 (the thermal-removal method)
- **Link:** DOI **10.1016/j.ymssp.2012.08.026** (Elsevier, *Mech. Syst. Signal Process.* 35:16–34)
- **What to do:** get via your institution / library / ResearchGate author copy (ask the authors — it's routinely shared). Never need to pay if you can get a preprint
- **Unlocks:** the exact regression/cointegration recipe for removing the thermal common trend before alarming — the engine of roadmap #4

### 💰 4. Peeters & De Roeck 2001 — the Z24 temperature-vs-damage reference
- **Link:** DOI **10.1002/1096-9845(200102)30:2<149::aid-eqe1>3.0.co;2-z** (Wiley, *Earthquake Eng. Struct. Dyn.* 30(2):149–171)
- **What to do:** institutional access / request preprint
- **Unlocks:** the "~14% lowest-mode seasonal shift, dominated by temperature" number we cite; the citation we owe if we ship temperature normalization

---

## Tier 2 — high value, gated

### 🔐 5. FHWA Long-Term Bridge Performance (LTBP)
- **Link:** https://highways.dot.gov/research/long-term-infrastructure-performance/ltbp/long-term-bridge-performance
- **What it is:** the US flagship longitudinal bridge-condition program (NDE data, deterioration over years)
- **What to do:** submit a **data-use request** through FHWA (data-use agreement); not self-service
- **Partial ✅ 2026-08-14:** the *public* **InfoBridge "Selected Bridges" export** already arrived and is analyzed → `scripts/ltbp_analyze.py` → `data/ltbp/analysis/ltbp_report.md` (44 LTBP pilot bridges, real longitudinal 1993–2025 → **empirical Markov priors**; 1,892-bridge fleet → cross-sectional condition-vs-age). ⚠️ Data quirk: the export's "58 - Deck Condition Rating" field is a saturated 0/1 code (not the real NBI deck rating) — use super/sub only. Still to do: the full gated LTBP data-use dataset (NDE, richer longitudinal)
- **Unlocks:** real longitudinal deterioration data to inform the **Markov priors** (roadmap #8) instead of only literature values — ✅ now in-repo

### 🔐 6. Cesium ion (free tier) — for georeferenced 3D
- **Link:** https://cesium.com/ion/ (sign-up at ion.cesium.com)
- **What it is:** cloud-hosted world terrain/building tiles for CesiumJS; **requires a free account + an access token**
- **What to do:** one person signs up (free Standard tier), creates an access token, paste it into the frontend `.env` (e.g. `VITE_CESIUM_TOKEN=…`), **never commit it**
- **Unlocks:** roadmap **#10 visualization** — removes the "bridge floating in a black void" fake look with real terrain context

### 🔐 7. E-Defense (NIED Japan) shake-table data *(optional)*
- **Link:** https://www.bosai.go.jp/ (search "E-Defense data") — NIED runs a data-use-agreement registration portal
- **What to do:** verify current portal; register if we want the calibration corpus
- **Unlocks:** full-scale shake-table test records as validation ground-truth for the vibration pipeline (roadmap #5/#7). **Low priority** — nice-to-have, not load-bearing

---

## Tier 3 — open, no credentials (just download, or already have)

### 🌐 8. Noto earthquake bridge point-cloud dataset (Japan)
- **Link:** https://doi.org/10.50915/data.jsceiii.27948816.v2 — **CC BY 4.0**, ~10 GB, E57 LiDAR point clouds of bridge digital-twin seismic-emergency inspection
- **Unlocks:** a **real** post-disaster scan layer for the reality-capture / "scan on the twin" demo (roadmap #14). Download when needed — it's big

### 🌐 9. COST 323 weigh-in-motion report + FHWA Traffic Monitoring Guide
- **Link:** COST 323 final report (Weigh-in-Motion of Road Vehicles, 1999/2002 — open PDF) · https://www.fhwa.dot.gov/policyinformation/tmguide/
- **Unlocks:** the GVW distributions + accuracy classes (A(5)/B(7)/C(10)) and 13-class scheme behind realistic traffic (roadmap #9)

### ✅ 10–13. Already in the repo — no action
- **CrackSeg9k** (CC0 crack images, `data/cv/crackseg9k`) · **HBTA** vibration · **Z24 replay** (`data/z24/inputs.npy`, 991 MB) · **SDNET2018** (registration-gated, dev-only) · **dacl10k** (CC BY-NC, dev-only)
- **Live public-MQTT broker** — already wired (`bridge=live-demo`), no credentials

---

## Paywalled method papers (fetch if convenient; else preprints)

| Topic | Reference | DOI |
|---|---|---|
| Pontis Markov decision process | Golabi & Shepard, *Interfaces* 1997 | 10.1287/inte.27.1.71 |
| Markov deterioration | Cesare et al., *J. Infrastruct. Syst.* 1992 | (via ASCE) |
| Bayesian updating of deterioration | *J. Bridge Eng.* 2020 | 10.1061/(asce)be.1943-5592.0001530 |
| Crack-width criteria | ACI 224R (flexural crack widths 0.004–0.006 in) | aci.org |
| Sensor noise floors | Ragam & Sahebraoji 2019, IET WSS | 10.1049/iet-wss.2018.5099 |

**Rule of thumb:** prefer the ResearchGate/author copy or your institution's library before buying; we need the *method*, not the journal issue.

---

## What I'll do the moment each arrives
- **Z24 package** → build the temperature-normalization overlay + the Z24-grounded seeded-defect demo; a real OMA pipeline test
- **S101 login** → calibrate our frequency-tracking output against a real reference; port the control-chart conventions
- **Cesium token** → georeference the twin (terrain + buildings), wire it into the 3D scene — ✅ **token stored** in `twin/.env` (gitignored), validated against ion API (World Terrain + Google Photorealistic 3D Tiles + OSM Buildings available)
- **LTBP / COST 323** → Markov priors and traffic GVW distributions from real evidence — ✅ **Markov priors done** (InfoBridge export, see #5)

*Written 2026-08-14. Registration details verified live; paywalled DOIs from the 11-agent research workflow.*
