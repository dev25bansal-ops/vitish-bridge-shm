---
tags: [research, facts, vitish-2026, shm]
created: 2026-08-13
---

# Verified Facts — the correction list (master plan §3.2)

Everything ✓ was confirmed against a live primary source on 13 Aug 2026. Anything here is safe to quote. Anything NOT here is suspect.

## The corrections you must make

- **Morbi** — pedestrian **suspension** bridge over Machchhu river, 230 m × 1.25 m, built 1880s; reopened 26 Oct 2022 (5 days before collapse) **without a fitness certificate**; capacity 125, >500 on it (~4× overload), 3,165 tickets sold; forensic report: **rusted cables, broken anchors, loose bolts, heavy new flooring**; 9 Oreva-linked arrests; official toll **~135 (55 children) / Wikipedia "at least 141"**.
- **Brazil** — Tocantins River bridge collapsed **22 Dec 2024** (13 dead), NOT March 2025. DNIT flagged cracks/pillar inclination in 2020; a May 2024 renovation tender never proceeded → the predictive-maintenance hook.
- **Z24** — 58 m (not 60 m); first modes ~3.5–4.5 Hz (Peeters & De Roeck 2001); environmental paper has **>1,000 citations**; IASC-ASCE benchmark ≈ 463. Damage timeline: settlement 20→95 mm (10–18 Aug 1998), spalling (25–26 Aug), hinge failure (31 Aug), anchor-head (2–3 Sep), tendon rupture (7–9 Sep). See [[Z24-Benchmark]].
- **IRICEN** uses numeric CRN **0–6** ratings, not color codes.
- **SDNET2018** is classification-only — cannot train YOLO-seg masks directly ([[CV-Model]]).
- **primus29/crackseg** is CLIPSeg, NOT YOLOv8 weights — never cite it as YOLO.
- **Encardio** now has an AI platform (Proqio); **HBM is now HBK** (Monitor360 "Powered by AI"); **NI is Emerson T&M** (InsightCM is rotating-machinery CM, not bridge SHM).
- **Jetson Nano** ~30 FPS → realistically **8–15 FPS** for YOLOv8n-seg@640; quote an Orin Nano number or drop it.
- **QoS** — pick one: QoS 1 for telemetry, **QoS 2 for alarms** (old report said both; fixed in [[Message-Contract]]).
- **Latency** — ~200 ms is **streaming telemetry only** (10+30+50+100=190 ms). Anomaly needs a full **10.24 s window** → **~10.5 s + inference**. State both deliberately ([[Metrics]]).

## Never quote (UNVERIFIED)

- "EU/UK/Netherlands mandate smart sensors" — no such mandate verified.
- "~1 million bridges in Europe/China".
- "42,000 structurally deficient" — term retired in 2022; use **"poor condition"**.
- "4 corroded cables" and "18 days before failure" for Morbi.
- "$10–50/bridge/month" competitor pricing — none publish pricing.
- "Rio Jiparaná / March 2025" collapse — does not exist.

Related: [[Z24-Benchmark]] · [[Datasets]] · [[Global-Failures]] · [[India-Policy]]
