---
tags: [demo, qna, vitish-2026, shm]
created: 2026-08-13
---

# Q&A Defense — 12 canned answers + fixes

## Standing rule

> Never claim a number or feature stronger than what's in the repo. Honesty reads as confidence.

## Fixes to the report's old 20 questions

- **#5:** "dacl10k is naturally balanced" is FALSE — crack dominates; it's **multi-label + imbalanced**. Say: focal loss + class weights. SDNET2018 IS balanced 50/50.
- **#7:** Reconcile FPR 4% with mean+3σ (theoretical 0.13%): the healthy-error distribution is **non-Gaussian**.
- **#8:** BHI weights are a **design choice** reflecting evidence reliability (re-calibrated on pilot data) — NOT "swept on the Z24 test set" (incoherent: Z24 has no images).
- **#12:** Latency splits into **~200 ms streaming vs ~10.5 s + inference anomaly**; pick QoS 1 or 2, not both.
- **#16:** Reconcile $5–15/mo vs $46.7/mo TCO, $500 vs $560/yr, $300 vs $588 hardware (state the MPU6050-class downgrade explicitly).
- **#19:** Replace "would have flagged Morbi weeks early" with the reframe in [[Storyboard]].
- **Q3/Q4 (2026-08-15):** Q4 previously claimed "the official .mat files under the KU Leuven license" — **registration is NOT done**, we use the MIT-licensed processed mirror, scenario names are chronology-inferred. Q3 previously claimed "we reliably catch settlement ≥4 cm, spalling, tendon rupture" — the measured per-scenario recall is **0.002** ([[Metrics]]); only the demo healthy-vs-rupture envelope separates (1.0). Both answers rewritten to say exactly that.

## The 12 canned answers (verbatim)

**Q1 — Temperature shifts frequencies ~9% on Z24 itself. How do you separate damage from weather?**

"This is our biggest validated risk. Our 3σ threshold is calibrated on healthy windows spanning a full environmental cycle; we feed temperature-compensated features and log temp/humidity as co-variates (they're in the BOM). We don't claim environmental robustness was proven in 36 hours — de-confounding is the pilot's first validation task."

**Q2 — Prove your system would have prevented Morbi. Where is the Morbi data?**

"We never claim validated prevention — Morbi had no sensors, so it cannot be a test set. What Z24 proves is that our detector flags documented progressive damage ~N days before the final rupture scenario. Morbi is our motivation; its mode — cable-anchorage corrosion under overload — is a known blind spot of global-vibration monitoring, which is why our roadmap adds cable-strain and acoustic sensing."

**Q3 — FPR 4% means 2 of 50 bridges are always red (alarm fatigue). What's your miss rate on EARLY damage like the 2 cm settlement?**

"We'll show both confusion matrices, and the honest headline is that the raw per-window Z24 classifier does **not** separate subtle progressive stages — measured recall **0.002** on the 17-scenario benchmark ([[Metrics]]). What does separate cleanly is our demo's healthy-vs-rupture envelope (precision/recall **1.0** at mean+3σ) — that is the staged rupture arc, and we do **not** claim it catches a 2 cm settlement. A miss is fatal and a false alarm only costs inspection time, so the production BHI never leans on vibration alone: it fuses CV + load, weights visual evidence higher, requires confirmation before any closure recommendation, and tracks early-stage sensitivity as a documented pilot metric."

**Q4 — Z24 needs a signed KU Leuven research agreement. Did you sign it? Is that HuggingFace copy authorized?**

"Honest answer: **no, we have not completed the KU Leuven registration.** We work from a publicly mirrored, **MIT-licensed** processed copy (`thanglexuan/Z24-dataset-processed` — provenance in [[Z24-Benchmark]]), not the official .mat release, and the mirror omits a label legend, so our per-scenario names are *chronology-inferred*, not confirmed against the portal. We treat any published benchmark claim as provisional until we register and verify against the official release — which is also why the demo never fuses this data into a live production BHI. A commercial pilot would license/register properly and transition to self-captured data."

**Q5 — Z24 is a Swiss concrete highway bridge; Morbi was a steel suspension footbridge. What transfers?**

"Nothing directly, and we never claim it does. Z24 is proof-of-method on real, citable progressive-failure data; a production system trains per structure type, then per bridge, on its own baseline. The fusion weights, BHI, and twin are structure-agnostic."

**Q6 — Is any of this live? Show a packet from your ESP32. Where did the 49 bridges come from?**

"We disclose it openly: the hero bridge streams the benchmark through the real MQTT-to-WebSocket pipeline; the ESP32 path is shown live if the bench passes (and it passed today / we ran it in the lab). The 49 other bridges are illustrative — real locations from US NBI/OSM with simulated health — shown to demonstrate the regulator view. The screen labels every source."

**Q7 — How did you compute F1 0.85? Didn't you inflate it by labeling everything after damage onset positive?**

"Definition: windows are 10.24 s @ 100 Hz; positive = reconstruction error > mean + 3σ of the healthy-only envelope; test set is the Z24 damage-stage windows broken out per scenario. Here's the confusion matrix and the threshold-vs-FPR curve. We don't present 0.85 as measured until it is."

**Q8 — Your unit economics don't add up ($588 hardware ≠ $300; $46.7/mo TCO vs $5–15/mo SaaS).**

"Fair challenge — the discount line was sloppy. The $300 scale figure assumes a deliberate sensor downgrade (ADXL355 ~$30 → MPU6050-class ~$2), trading some vibration fidelity for cost — we should have stated it. The correct SaaS framing is platform-plus-services priced above amortized TCO: at 1,000 bridges recurring cost is ~$260/bridge/yr, so a realistic price is $25–30/bridge/month, not $5–15. We corrected the tables."

**Q9 — What inspection standard does your 0–100 BHI map to (IRC SP-99 / FHWA NBIS / IBMS 0–9)?**

"The 0–100 BHI is a Caltrans/AASHTO element-condition-state construct; our component weights follow the same aggregation logic, and a calibration study against IBMS condition ratings (CRN 0–6 per IRICEN) is explicitly a pilot deliverable. Our sub-indices are auditable — each maps to a measurable (crack area, anomaly score, utilization)."

**Q10 — 30+ days on one 18650 at 100 Hz continuous WiFi streaming? How do 10 nodes sync clocks across a 100 m span?**

"Continuous streaming is ~1 day per 2600 mAh cell — we duty-cycle: 2-s bursts at 100 Hz every 60 s, ~3 mA average, ~37 days per cell; a 2 W panel over-provisions that 20×. Clock sync: each node timestamps and we align on the broker; for modal analysis we use a shared-sampling protocol — and our demo uses the benchmark's already-synchronized channels."

**Q11 — What does BHI = 78 mean physically, and how was the 78→34 curve derived?**

"78 = near-as-built health on a 0–100 scale where 100 is as-built and 0 is no remaining value, aggregated from condition-state sub-indices. The 78→34 curve is the model's output on the damage scenario — driven by rising crack severity + anomaly score crossing threshold; the green/amber/red bands translate it to action."

**Q12 — Is the demo real or pre-recorded?**

"Everything is live from the local stack. We recorded a backup video and have screenshots as contingency — but the demo you're watching is the real pipeline: the MQTT broker is local, the models run here, and the data source is labeled on screen. The git history shows the build hour by hour."

Related: [[Storyboard]] · [[Metrics]] · [[Verified-Facts]] · [[BHI-Formula]]
