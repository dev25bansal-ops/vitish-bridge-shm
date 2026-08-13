# VITISH 2026 · Master Build Plan
## PS #99 — AI-Based Structural Health Monitoring for Bridges & Public Infrastructure

**Team:** 6 members · **Build window:** 36 hours · **Demo:** 6 minutes (Morbi-anchored storyboard)

Built from: (1) full read of the VITISH research report, (2) a 12-agent global research workflow (10 research agents + 2 adversarial audits, ~968k tokens, 774 tool calls, all sources fetched live on 13 Aug 2026), (3) the two audits' corrections.

---

## 0. How to use this document

- **Section 1** — read first. The 10 decisions that changed from the report (and why).
- **Sections 4–9** — the frozen architecture, stack, data, ML, twin, and hardware. These are the *decisions*; the build follows them literally.
- **Section 11** — the hour-by-hour 36-hour plan with hard gates.
- **Section 12** — do everything here *before* H0. This is what makes the 36h survivable.
- **Sections 13–15** — the demo script (facts corrected), the Q&A defense (12 canned answers), and the risk register.
- Everything with a **✓ VERIFIED** tag was confirmed against a live primary source on 13 Aug 2026. Anything flagged **UNVERIFIED** must not be quoted on stage.

---

## 1. Executive summary — the 10 decisions that changed from the report

The report is strong theater but contained claims a hostile judge could dismantle. Both adversarial audits independently confirmed the core plan is viable **only if you pre-build** and **only if you fix these 10 things**:

| # | Report said | Master plan says | Why |
|---|---|---|---|
| 1 | 8h to train YOLOv8-seg on dacl10k (18 classes) | **Binary crack segmenter on SDNET2018 during the 36h**; dacl10k is a *pre-hackathon* fine-tune only | dacl10k is 18-class, heavily imbalanced, **multi-label semantic** segmentation (baseline mIoU only 0.42; cracks poorly scored). COCO/RLE mask→YOLO-seg conversion is a 2–4h fiddly step and overlap breaks YOLO's single-label assumption. SDNET2018 (56k × 256×256 binary images, 50/50 balanced) trains in ~2–4h on one GPU and gives *clean, judge-visible* overlays. |
| 2 | LSTM-AE on raw Z24 acceleration | **LSTM-AE (or VAE+OCSVM) on temperature-compensated Z24 features** | Z24's modal frequencies swing ~10% with seasonal temperature (the benchmark's own purpose) while damage shifts them ~1–2%. A raw AE will flag *weather* as damage live, and miss the scripted damage onset. Regress temperature out (or feed it as an input channel). Calibrate the threshold on the full ambient year, not a clean clip. |
| 3 | YOLOv8-seg | **YOLO26s-seg** (Jan 2026, +2.2 mask mAP over v8s) with YOLO11s as fallback | By mid-2026 YOLOv8 is 3 generations old and a judge can ask "why not YOLO12/26?" Upgrade is a one-line swap in Ultralytics. |
| 4 | LSTM-AE as the headline vibration model | **VAE+OCSVM as primary** (verified PR 0.996 / recall 0.999 on Z24, Scientific Reports 2025); LSTM-AE as edge baseline; **MiniRocket+Ridge as zero-training fallback** (Elios-Lab pretrained weights) | Same pipeline, strictly better published numbers, and it gives you a canned answer to "why this model?" |
| 5 | "Every sensor is live" (ESP32 hardware) | **Replay-first, live-second.** All four subsystems consume a recorded Z24 replay through the real MQTT→DB→inference→twin pipeline. One real ESP32-S3 + ADXL355 node is a *stretch goal* shown only if a pre-demo smoke test passes | Venue WiFi, batteries, sensor noise, and MQTT unreachability are the classic demo-killers. A deterministic replay is a 100% safety net; the live node is a garnish. The 100 Hz claim stays fully supportable (it is Z24's actual rate). |
| 6 | Black-box weighted BHI | **Transparent BHI**: 3 sub-indices (visual crack severity, vibration novelty, load/utilization), fixed defensible weights, green/amber/red thresholds, **plus an uncertainty band** (MC-dropout/ensemble spread) | The 0–100 BHI is a real Caltrans/AASHTO construct — keep it, but present it as element-condition-state aggregation, not an opaque formula. "High uncertainty → flag for human review" answers the #1 trust question. |
| 7 | R3F twin as a 36h build from scratch | **Pre-built twin shell** (scene, camera, HUD) with **pinned versions** (R3F ^9.7.0 + React ^19.2.8 + three ^0.185.1 + @types/three ^0.185.4). During the 36h, wire only 3–4 live bindings | React 19.2.x broke the R3F reconciler <9.5; three 0.185 ships **zero .d.ts** (needs @types/three). Version churn eats 2–4h. Pre-build the shell; the 8-hour budget inside the 36h is the *wiring* budget. |
| 8 | "Would have flagged Morbi weeks early" / "one click could have prevented Morbi" | **Reframe.** "Z24 proves we catch documented progressive failure N days early. Morbi is our *motivation* — and its mode (overload + cable-anchorage corrosion) is a known blind spot of global-vibration monitoring, which is why our roadmap adds strain/acoustic sensing." | Morbi had no sensors → it is untestable as a validation case, and structurally it is the *opposite* of Z24's induced damage. This is the single most dangerous overclaim in the report; the reframe turns a kill-shot into differentiation. |
| 9 | USD 560/bridge/yr; $5–15/bridge/mo SaaS; "$300 hardware after 40% bulk discount" | **Reconciled:** pilot BOM ≈ $980 (10 nodes); scaled ≈ $260–300/bridge/yr with an explicit sensor-grade downgrade (ADXL355→MPU6050-class); SaaS priced **above** amortized TCO at ~$25–30/bridge/mo | The $300 figure was wrong arithmetic (0.6 × $980 = $588, not $300); $5–15/mo sells below the $46.7/mo all-in TCO. A business-savvy judge will do this math. |
| 10 | Morbi = 135 dead, cable-stayed, "4 corroded cables", "18 days before failure" | **135 (some tallies cite 141)**, **pedestrian suspension bridge**, drop the "4 cables" and "18 days" claims | "18 days" appears in no Z24 analysis (honest lead time ≈ 30 days to rupture from first settlement, ≈ 15 days from spalling). The forensic report says cables were "rusted" with broken anchors and loose bolts — no source says exactly 4. |

**The single biggest structural insight from the audits:** *every* failure mode above is mitigated by the same move — **pre-build everything that can be pre-built** (data, models, twin shell, Docker Compose, message contract, demo script) in the ~2 weeks before the hackathon, so the 36 hours are *integration, tuning, and rehearsal*, not *discovery*.

---

## 2. The thesis & pitch hook

**One line:** "The Government of India has already chosen our architecture — MoRTH's IBMS digital survey plus the IIT Madras / C-DAC National Bridge Health Monitoring System is a 1:1 match to our IoT + AI + digital-twin stack. We're building the open, low-cost reference implementation."

**Verified policy anchors (all live as of 13 Aug 2026):**

- **MoRTH circular, 25 Jun 2026** ✓ — nationwide **IBMS digital inventory + condition survey** of ~1.7 lakh National Highway bridges; **deadline 30 Sep 2026**. This is a live, dated, urgent procurement event the team can cite.
- **IIT Madras + C-DAC MoU, 9 Jul 2026** ✓ — centralized **National Bridge Health Monitoring System (NBHMS)**. The report's 4-layer stack (sensors → comms → AI → twin) mirrors what a national authority is now building.
- **NHAI Teesta / Mahananda BHMS tender ₹11.69 crore** ✓ — bridge health monitoring is being bought *today* in India.
- **ISHMS Guidelines v1, 16 Jul 2025** ✓ — the regulatory playbook for integrated SHM.
- After Gambhira (22 dead, 9 Jul 2025) Gujarat inspected **1,800+ bridges → 20 fully closed, 113 partially closed** ✓ — the single best segue from "reactive mass inspection" to "continuous monitoring".

**Global significance (verified, citable):**
- 52 dead — Meizhou expressway, China, 1 May 2024 ✓
- 38 dead — Shangluo road bridge, Shaanxi, 19 Jul 2024 ✓
- 141 (per Wikipedia) / 135 (official) — Morbi, 30 Oct 2022 ✓
- 22 dead — Gambhira Bridge, Gujarat, 9 Jul 2025 ✓
- 13 dead — Tocantins River bridge, Brazil, **22 Dec 2024** (NOT March 2025 — the report's date was wrong) ✓
- 12 dead — Jianzha Yellow River bridge, China, 22 Aug 2025 ✓
- 6 dead — Baltimore Key Bridge, 26 Mar 2024 (ship strike; $1.7B/wk supply-chain disruption) ✓
- Systemic: US **623,218** bridges; **~41,600 "poor condition"** carrying 163M crossings/day (FHWA NBI, Jun 2025); **1 in 3 needs repair** (ARTBA 2025); ASCE 2025 grade **C**, 6.8% poor, and 49.1% fair (the silent aging-downgrade pool) ✓
- **170 collapses / 202 deaths / 441 injured, India 2021–2025** (Newslaundry) ✓ — vs MoRTH's official log of only 42 collapses 2019–24. Be ready for the government-vs-media discrepancy in Q&A.
- Market: Business Research Company — **$3.44B (2025) → $3.96B (2026), ~15% CAGR**. Q&A caveat: estimates range ~$2B–$9B by firm/scope. ✓

**Do NOT claim (UNVERIFIED):** "EU/UK/Netherlands mandate smart sensors" (no such mandate could be verified); "~1 million bridges in Europe/China" (unverified); "42,000 structurally deficient" (term retired in 2022 — use "poor condition"); "4 corroded cables"; "18 days before failure"; "$10–50/bridge/month" for competitors (none publish pricing).

---

## 3. Verified research base (confirmations & corrections)

### 3.1 Confirmed live datasets (the build's fuel)
| Dataset | What it is | Status |
|---|---|---|
| **Z24 Bridge** (KU Leuven benchmark) | 1-year ambient monitoring (Nov 1997–Sep 1998) + staged progressive damage; Swiss 58 m 2-cell post-tensioned box girder, 100 Hz, 27 channels | ✓ Official portal (bwk.kuleuven.be/bwm/z24) **requires registration review** — do not depend on it. **Use the Hugging Face processed mirror instead** (below). |
| **Z24 processed mirror** (HF) | `inputs.npy` (1530, 27, 6000) float64 m/s² + `labels.npy` (1530,), 17 scenarios × 9 setups × 10 segments; ~992 MB; MIT license | ✓ Verified: `huggingface.co/datasets/thanglexuan/Z24-dataset-processed` and mirror `Sagarr123/Z24-dataset-processed`. **Download via direct resolve URLs, NOT `load_dataset()`** (ConfigNamesError). Each 60-s recording = 10 × 6000-sample segments. |
| **dacl10k** | Bridge damage segmentation, WACV 2024 (Flotzinger/Rösch/Braml, arXiv:2309.00460); ~9,920 images, 512×512, **multi-label semantic**, ~18–19 classes (12–13 damage + 6 components); best published mIoU **0.42**; CC BY-NC 4.0 | ✓ Live (HF + GitHub toolkit `phiyodr/dacl10k-toolkit`). v3 split ≈ 6,935 train. **Non-commercial license** — fine for a hackathon, disclose in Q&A. |
| **SDNET2018** | 56,000 × 256×256 **binary** (crack / no-crack), balanced, crack widths 0.06–25 mm | ✓ Live. IEEE DataPort correct slug: `sdnet2018-concrete-crack-image-dataset-machine-learning-applications` (the report's URL 404'd). **No pixel masks** — classification/pretraining only. |
| **Ultralytics crack-seg dataset** | Official small crack segmentation set, 91.6 MB | ✓ Live — the guaranteed 2-hour baseline. |
| **Vänersborg (DiB, Sweden)** | 64 bridge openings, **CC BY 4.0**, KTH/IoTBridge, Zenodo 8300494 (redirects to 8300495) | ✓ Live. **No damage ground-truth labels** — honest use is a reconstruction-error sanity check, NOT cross-bridge F1. |
| **US NBI** | 624,193-bridge inventory (FHWA) | ✓ For the 50-bridge regulator-map real locations. |
| **Elios-Lab Z24 repo** | Reference pipeline + **pretrained weights** | ✓ Active. NOTE: its `Z24_Bridge_env.yml` **404s** (README setup fails) and it is a **supervised multi-class damage-stage classifier**, not an unsupervised LSTM-AE — cite it as a reference, not as the AE source. |

### 3.2 Corrections you must make in the deck
1. **Morbi**: pedestrian **suspension** bridge over Machchhu river, 230 m × 1.25 m, built 1880s; reopened 26 Oct 2022 (5 days before collapse) **without a fitness certificate**; capacity 125, **>500 on it (~4× overload)**, 3,165 tickets sold; forensic report: **rusted cables, broken anchors, loose bolts, heavy new flooring**; 9 Oreva-linked arrests; IPC 304 FIR. Death toll: **official ~135 (55 children per Indian Express) / Wikipedia "at least 141"**.
2. **Brazil**: Tocantins River bridge collapsed **22 Dec 2024** (13 dead); DNIT flagged cracks/pillar inclination in **2020**, May 2024 renovation tender never proceeded → perfect predictive-maintenance hook. **Delete any "March 2025 / Rio Jiparaná" claim** (no such collapse exists).
3. **Z24**: 58 m (not 60 m); modal first modes ~3.5–4.5 Hz (Peeters & De Roeck 2001); environmental paper has **>1,000 citations** (not "690"); IASC-ASCE benchmark ≈ 463 citations (not "690"); progressive damage timeline: pier settlement 20→95 mm (10–18 Aug 1998), spalling (25–26 Aug), hinge failure (31 Aug), anchor-head (2–3 Sep), tendon rupture (7–9 Sep).
4. **IRICEN** uses numeric CRN **0–6 ratings**, not color codes.
5. **SDNET2018** is classification-only — cannot train YOLO-seg masks on it directly; dacl10k semantic masks must be converted to connected-component instance masks.
6. **primus29/crackseg** is **CLIPSeg**, not YOLOv8 weights — do not cite it as YOLO.
7. **Encardio now has an AI platform (Proqio)** — do not claim "no AI". **HBM is now HBK (Monitor360 "Powered by AI")**. **NI is Emerson T&M** (InsightCM = rotating-machinery CM, not bridge SHM).
8. **Jetson Nano ~30 FPS** claim → realistically **8–15 FPS** for YOLOv8n-seg@640; use an Orin Nano number or drop it.
9. **QoS inconsistency**: report §4.2 says QoS 2 for critical alerts, Q&A #12 says QoS 1 — pick one (recommend QoS 1 for telemetry, QoS 2 for alarms).
10. **Latency**: ~200 ms is true only for streaming telemetry (10+30+50+100=190 ms defensible). Anomaly detection needs a full **10.24 s window** (1024 samples @ 100 Hz) → **~10.5 s + inference**. State both deliberately.

### 3.3 The competitive gap (your wedge)
No major SHM vendor offers all four components (wireless IoT + CV + digital twin + predictive AI) in one open system:
- **IoT-only:** Resensys (SenSpot), SENSR (CX1), Campbell Scientific (wired loggers), Geokon (vibrating-wire + LoRa), Senceive (FlatMesh) — none have CV, twin, or ML anomaly.
- **AI-assessment-only:** Sensequake (consulting, site visits, no always-on).
- **Enterprise-twin-only:** Bentley iTwin (**$199/mo Standard / $499/mo Premium, verified**), Autodesk Tandem, Esri, Willow — BIM/geospatial-heavy, credit-metered, none pair live MEMS + ML + CV.
- **Service-heavy:** Strainstall, Encardio/Proqio.
- **India AI SHM:** SPPL India (IIT Delhi, OSHMAS) — hardware+service heavy, closed stack. You are **not** first-mover; your wedge is **open, dataset-driven, low-cost, 4-in-1**.
- Open-source foundations to cite: **PySHM, pyOMA2** (OMA/modal math), OpenBDLM.
- Flagship deployments to name-drop: Sydney Harbour **2,400+ sensors**; Hong Kong **~900 sensors on 3 bridges (US$1.3M)**; Queensferry Crossing 2,000+ planned; Millau fiber-optic — position your ESP32 tier as the low-cost mass-deployable layer beneath these.

---

## 4. Final architecture (frozen)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 · EDGE / SENSING                                                   │
│  • Z24 Python replay simulator = PRIMARY (Day-1 deliverable, ~150 lines)     │
│    - loads inputs.npy/labels.npy, publishes nodes 6–8 (of 27 channels)      │
│    - batched 100-sample JSON payloads, 1 msg/s/node (6–8 msgs/s total)       │
│    - damage injector: switches undamaged→tendon-rupture at a storyboard beat │
│    - ~5% amplitude jitter + occasional packet drop (robustness)              │
│  • REAL node (stretch goal): ESP32-S3-DevKitC-1 + ADXL355 eval board         │
│    - computes rolling RMS anomaly flag locally (20 lines) + publishes raw    │
│  • Optional camera prop: Pi Zero 2 W + Camera Module 3 (stream-only, JPEG)   │
└─────────────────────────────────────────────────────────────────────────────┘
                              │  MQTT (paho-mqtt)
┌─────────────────────────────▼───────────────────────────────────────────────┐
│  LAYER 2 · COMMUNICATION                                                    │
│  • Mosquitto broker LOCAL on demo laptop (zero venue-WiFi dependency)       │
│  • Topics: bridge/{id}/accel, bridge/{id}/flag, bridge/{id}/frame,          │
│            bridge/{id}/bhi; QoS 1 telemetry / QoS 2 alarms (pick one—QoS 1) │
│  • Simulated LoRa topic bridge/span-7/rf labelled as backhaul                │
│  • (Optional) free HiveMQ Cloud for a "remote streaming" beat               │
└─────────────────────────────▼───────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 3 · AI PROCESSING (dev laptop / server, never on-device)             │
│  CV branch        : YOLO26s-seg (fallback YOLO11s) — BINARY crack seg        │
│                     (SDNET2018 during 36h; dacl10k pre-trained baseline)    │
│                     + optional SAM2 refinement for hero masks                │
│  Vibration branch : VAE+OCSVM primary (PR 0.996 / recall 0.999, Z24)        │
│                     LSTM-AE edge baseline on temp-compensated features      │
│                     MiniRocket+Ridge = zero-training fallback (pretrained)  │
│                     → anomaly score + uncertainty (MC-dropout/ensemble)     │
│  Fusion           : BHI = f(crack_severity, vib_novelty, load) — transparent│
│                     weights, green/amber/red + uncertainty band              │
└─────────────────────────────▼───────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 4 · DIGITAL TWIN & DASHBOARD                                         │
│  • React Three Fiber v9 + React 19.2 + three 0.185 (pinned)                 │
│  • PARAMETRIC Morbi-style suspension bridge (no downloaded GLB)              │
│    → collapse-replay animation is data-driven (cable break, deck sag,        │
│      sensor cascade, BHI 87 → 12)                                            │
│  • zustand store ← WebSocket ← broker; instancedMesh sensor markers;         │
│    drei Html popup + Recharts spectrum (256-pt window)                       │
│  • MapLibre GL 6 + OpenFreeMap 50-bridge regulator view (health-colored)     │
│  • LLM copilot pane (SHM-Agents style) → plain-language maintenance advice   │
│  • Postgres (plain, Docker) persists history; offline fixture generator      │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Message contract (freeze on Day 0 before any coding):**
```json
// bridge/sensor-07/accel  (1 msg/s)
{ "bridge": "z24", "node": 7, "ts": 1786..., "fs": 100, "samples": [0.012, ...100 floats], "rms": 0.083, "flag": 0 }
// bridge/z24/bhi  (1 msg/s)
{ "bridge": "z24", "ts": ..., "bhi": 82.4, "u": 3.1, "cv": 0.35, "vib": 0.12, "load": 0.4, "state": "GREEN" }
```

---

## 5. Tech stack (exact, verified versions)

**Backend / data (Python 3.10+ venv):**
- paho-mqtt, numpy, scipy, pandas, scikit-learn (OCSVM), torch (VAE/LSTM-AE), ultralytics (YOLO26/YOLO11), psycopg2, python-dotenv
- Mosquitto (or EMQX in Docker), **plain Postgres** in Docker (skip TimescaleDB hypertables — a 36h demo doesn't need them; audit simplification)
- pyoma2 / PySHM as OMA/modal math references (citelits, not deps)

**Digital twin / dashboard (npm — pin these exact ranges, all verified React-19-compatible 13 Aug 2026):**
```json
dependencies: {
  "react": "^19.2.8", "react-dom": "^19.2.8", "three": "^0.185.1",
  "@react-three/fiber": "^9.7.0", "@react-three/drei": "^10.7.8",
  "zustand": "^5.0.14", "recharts": "^3.10.1", "maplibre-gl": "^6.3.0"
},
devDependencies: {
  "vite": "^8.2.0", "@vitejs/plugin-react": "^6.0.5", "typescript": "~6.0.2",
  "@types/react": "^19.2.18", "@types/react-dom": "^19.2.4",
  "@types/three": "^0.185.4", "@types/node": "^24.13.3"
}
```
Scaffold: `npm create vite@latest . -- --template react-ts` → `npm i` the above → Node 22 LTS or 24 LTS.
**Hard rules:** R3F ^9.7.0 with React ^19.2.8 — **never** R3F v10 alpha, **never** R3F v8. `@types/three` is mandatory (three 0.185 ships zero .d.ts). Keep TS on the template's ~6.0.2 (don't jump to 7.x mid-hackathon). Render text as HTML/CSS or drei `Html` — avoid drei `<Text>` (troika fetches a font from a CDN → offline hazard). **No CesiumJS** (141 MB package, ion token needed; MapLibre 6 is enough).

---

## 6. Data strategy (download BEFORE the hackathon)

| Data | Where | When | Verify |
|---|---|---|---|
| Z24 processed mirror (~992 MB) | `huggingface.co/datasets/thanglexuan/Z24-dataset-processed` (mirror: `Sagarr123/Z24-dataset-processed`) via direct resolve URLs | Day −14 (office WiFi, NOT venue) | print shapes: inputs (1530,27,6000), labels (1530,) |
| Z24 official .mat (for license story) | KU Leuven portal (registration) | Day −14 — **actually register** and keep the confirmation | email received |
| dacl10k v3 (~1.1 GB) | HF (toolkit: `github.com/phiyodr/dacl10k-toolkit`) | Day −14 | train ≈ 6,935 |
| SDNET2018 | IEEE DataPort correct slug | Day −7 | 56k imgs |
| Ultralytics crack-seg (91.6 MB) | Ultralytics assets | Day −3 | trains in 2h |
| Vänersborg / DiB | Zenodo 8300495 | Day −7 (optional sanity check) | 64 openings, no labels |
| US NBI coordinates (50 real bridges) | FHWA NBI | Day −7 | for the regulator map |

**Pre-compute before H0 (audit punch list):**
1. Convert dacl10k masks → YOLO-seg (COCO/RLE → single-label instance polygons). Use the **crack-only subset** for the demo model.
2. Pre-train baseline binary crack segmenter (yolov8s-seg / yolo11s-seg @ imgsz 512, ~50–100 epochs on one RTX 3060/4060-class GPU ≈ 2–4h).
3. Extract Z24 **hourly modal-frequency + temperature features** → cached `.npy` (thermal compensation).
4. Pre-train VAE+OCSVM and/or LSTM-AE; **validate that the anomaly score rises on the damage month and stays flat on temperature-only periods**.
5. Build the R3F twin shell (scene, camera, HUD) with pinned versions + mock-data mode.
6. Write + bench-test ESP32 Wi-Fi/MQTT firmware (before you need it live).
7. Commit Docker Compose (Postgres + EMQX/Mosquitto + app) — one-command stack spin-up.
8. Freeze the message contract (§4), BHI formula (§7), and the 6-min storyboard script.
9. Build the demo-driver replay tool (advances the storyboard timeline deterministically).
10. Copy ALL datasets, model checkpoints, and the twin shell to USB + a cloud backup. **Zero network reliance at demo time.**

---

## 7. ML methodology

### 7.1 CV — crack detection (component 2/4)
- **Primary (36h):** fine-tune a **binary crack segmenter** on SDNET2018 + crack-only dacl10k subset with **YOLO26s-seg** (or YOLO11s). Report **measured mAP@0.5** on a 70/20/10 split on screen — do NOT state 0.65 as fact (dacl10k's best published model is 0.42 mIoU; your own-split number will differ). Frozen backbone → fine-tune → evaluate on curated demo frames with visible cracks.
- **Pre-hackathon:** full dacl10k fine-tune (optional, for the "19-class model" talking point).
- **Mask pipeline (be ready to explain):** dacl10k provides *semantic* masks → connected-component → instance masks for YOLO-seg; SDNET2018 has no masks → classification/pretraining head only.
- **Fallbacks (zero training):** Ultralytics crack-seg weights; any of the verified HF pretrained crack models.
- **Judge defense:** "Why not just SAM2 out of the box?" → zero-shot foundation models plateau on real infrastructure (CiF benchmark, arXiv:2605.18413, ~25% mAP); we fine-tune on bridge-specific data. Optionally add a **SAM2 refinement pass** (SECrackSeg S-Adapter, Sensors 2025) for hero masks. "Why not YOLO12?" → we use YOLO26s (2026), neutralized.

### 7.2 Vibration — predictive maintenance (component 4/4)
- **Primary:** **VAE + OCSVM** on Z24 (verified: PR 0.996 / recall 0.999, Scientific Reports 2025). Unsupervised — perfect for "no labeled damage" story.
- **Edge baseline:** LSTM-AE with **MC-dropout** (uncertainty band, cite Sajedi & Liang arXiv:2004.05151).
- **Zero-training fallback:** MiniRocket + Ridge with Elios-Lab pretrained weights.
- **SOTA layer (cite, don't build):** self-supervised masked-autoencoder Transformer foundation model (Benfenati et al. 2025, arXiv:2404.02944, IEEE TSUSC — 99.9% AD accuracy in 15 windows vs PCA 95.03% in 120). Frame: "LSTM-AE on edge for latency; Transformer foundation model in cloud for accuracy" — mirrors the paper's own deployment story.
- **Critical: temperature compensation** (Section 1, #2). Regress temperature out of modal features (cite Neumann et al. arXiv:2409.17735) — this pre-empts the most likely judge question.
- **Anomaly definition (state explicitly):** 10.24 s windows @ 100 Hz; positive = reconstruction error > mean + 3σ of the **healthy-only** envelope spanning the full environmental year. Report the full confusion matrix per Z24 scenario, not a single F1. **F1 0.85+ / FPR 4% are build-time measured targets, not claims** (and mean+3σ on Gaussian data is 0.13% FPR — if your measured FPR is 4%, the healthy-error distribution is non-Gaussian; say so).

### 7.3 Fusion — the Bridge Health Index (the headline metric)
- **BHI 0–100** presented as **Caltrans/AASHTO element-condition-state aggregation** ("100 = as-built, 0 = no remaining value"), not a black-box formula. Cite the Caltrans BHI construct.
- **3 transparent sub-indices:**
  - `cv` = visual crack severity (0–1) from CV
  - `vib` = vibration novelty (0–1) from VAE/OCSVM anomaly score
  - `load` = utilization (0–1) from IoT/overload
- `BHI = 100 × (1 − w_cv·cv − w_vib·vib − w_load·load) × age_factor × traffic_factor` with **fixed, defensible weights** (e.g., 0.4/0.35/0.25 — reflecting evidence reliability; state they'll be re-calibrated on pilot data, NOT that they were "swept to maximize F1", which is incoherent since Z24 has no images).
- **Uncertainty band** on the BHI (MC-dropout/ensemble spread) → "high uncertainty → flag for human review."
- Green/amber/red thresholds (e.g., ≥70 green, 50–70 amber, <50 red).
- **Roadmap honest-claim:** "Z24 proves we catch documented progressive failure N days early" — derive N during the build from the actual first threshold-crossing (settlement 10 Aug → rupture 9 Sep ≈ 30 days; spalling 25 Aug ≈ 15 days) and label the source on screen.

### 7.4 The "wow" layer (cheap, 2026-fresh)
- **LLM copilot pane** (SHM-Agents style, arXiv:2605.12916): alert → plain-language maintenance recommendation. Mock with a local LLM or canned templates in the demo.
- **Federated learning** as a future-work slide (Feng et al. 2026, arXiv:2606.03084): "fine-tune across bridges without sharing raw sensor data."
- **Surveys to cite in related work:** Zhang & Liang domain adaptation (arXiv:2512.18780); Yang et al. deep generative SHM (arXiv:2507.15026).

---

## 8. Digital twin build (8-hour wiring budget inside the 36h)

**Pre-built before H0:** scaffold + pinned package.json (§5), parametric MorbiBridge component, camera rig, lighting, HUD, zustand store, ws client, offline fixture generator.

**During the 36h — strict order:**
1. `0:00–0:30` — verify pre-built shell runs in the venue environment; `npm run build && vite preview`.
2. `0:30–1:30` — wire WebSocket → zustand → mock data (offline-safe).
3. `1:30–3:00` — live bindings: 3–4 values (2 modal frequencies, temperature, BHI) with **amplified deflection (~100×)** so changes are visible.
4. `3:00–4:30` — instancedMesh sensor markers + raycast click + drei Html popup + Recharts spectrum (256-pt window).
5. `4:30–6:00` — MapLibre 50-bridge map (real US NBI locations, simulated BHI) + selection sync.
6. `6:00–7:00` — storyboard scenes: cable break, deck sag, BHI 87→12 sensor cascade; BHI gauge.
7. `7:00–8:00` — perf pass (`dpr={[1,1.5]}`, shadows off, frameloop='always', memo popups), **network-off test**, build + preview.

**Architecture rules (from the twin research):** parametric bridge from primitives (<10k tris), NOT a downloaded GLB (can't rig a static model for collapse replay; Sketchfab "Suspension Bridge" CC-BY is only set-dressing). One `<InstancedMesh>` for all sensors = 1 draw call. Browser-native WebSocket (no lib). Plain maplibre-gl (~60-line wrapper), **not** react-map-gl. **No Cesium.** Prewarm/cache map tiles at the venue or keep an SVG-map fallback.

---

## 9. Hardware plan (buy now, ~USD 90–130)

| Item | Buy? | Price | Notes |
|---|---|---|---|
| ESP32-S3-DevKitC-1 (N8R8) | ✅ 1× | ~$10–13 | The one real node. BLE 5 + PSRAM. |
| ADXL355 eval board (EVAL-ADXL355Z) | ✅ 1× | $56.95 (DigiKey ✓) | Only sensor that captures real ambient vibration (20–25 µg/√Hz). |
| — budget fallback — | | | BMI270 breakout ~$15 or GY-521 (MPU6050) ~$5 — but an MPU6050 on a desk outputs mostly its own noise; script the live demo around large low-freq motions. |
| Pi Zero 2 W + Camera Module 3 | ⚠️ optional | $15 + $25 | IoT-camera prop; stream-only (Zero 2 W cannot run YOLO real-time). Budget 2–3h setup. |
| 18650 2600 mAh + TP4056 + 2W solar panel | ⚠️ optional | ~$15 | Only if a "self-powered sensor" beat is wanted; one 18650 alone powers hours of streaming. |
| 2× Adafruit RFM95W | ⚠️ optional | $19.95 ea | LoRa prop, room-scale link only. |
| **Z24 simulator + laptop webcam + local Mosquitto + Postgres** | — | **$0** | The zero-risk default. Demo works with no hardware at all. |

**SKIP:** Dragino LG01 (~$200, single-channel SX1276 — not an 8-ch gateway), DJI Tello (**discontinued Jan 2024**, supply risk), Camera Module v2 (discontinued → Module 3), full LoRaWAN gateway, ESP32-CAM as primary (marginal quality; keep as ~$9 backup), 6× ADXL355 (simulate other channels from Z24 .npy).

**Range honesty:** do NOT claim a verified 10 km LoRa link. "LoRaWAN is the production backhaul; today's demo streams over WiFi/MQTT for reliability."

**Hardware hard-stop rule:** if the real node is not streaming by **hour 8** of the 36, cut it and run the simulator alone — the pipeline is byte-identical. (You did bench-test the firmware pre-hackathon.)

**Power math to quote:** 1% duty-cycled node ≈ 3 mA avg → a 2 W panel over-provisions ~20×; one 2600 mAh 18650 carries the live demo even streaming continuously.

---

## 10. Team roles (6)

| # | Role | Mandate |
|---|---|---|
| 1 | **Embedded / data pipeline** | Z24 replay simulator, MQTT, ESP32 firmware bring-up (H4–8 window), broker, Postgres |
| 2 | **CV / crack model** | YOLO26s-seg fine-tune, SDNET2018 pipeline, mask conversion, SAM2 (optional), live webcam hookup |
| 3 | **Vibration / anomaly ML** | VAE+OCSVM + LSTM-AE on temp-compensated features, threshold calibration, uncertainty, MiniRocket fallback |
| 4 | **Digital twin + dashboard** | R3F wiring, MapLibre map, BHI gauge, copilot pane |
| 5 | **Backend / integration OWNER** | Owns the single hero demo flow end-to-end, Docker Compose, message contract, demo-driver replay |
| 6 | **Presenter** | Owns the pitch script + deck from hour 0; **stops coding by ~H28** to rehearse |

All 6 must be able to explain their own component's data, training, and failure modes in 30 seconds. Use GitHub Issues for tracking; commit every 1–2h so the history shows honest continuous build work.

---

## 11. The 36-hour build plan (hour-by-hour, with hard gates)

### Phase 0 · H0–H2 — Freeze (parallel tracks start)
- [ ] H0: verify pre-built assets run in the venue environment; inventory GPU; smoke-test ESP32 on the local broker
- [ ] H0–H1: freeze stack, roles, the ONE hero demo flow, and the 90-second demo script — BEFORE meaningful code
- [ ] H1–H2: 3 parallel tracks start (embedded/backend · CV · vibration ML; twin track starts at H10)

### Phase 1 · H2–H10 — Core models (tracks 2 & 3), data pipeline (track 1)
- [ ] H2–H6: CV — fine-tune binary crack segmenter on SDNET2018/crack-subset (2–4h GPU), evaluate on demo frames
- [ ] H6–H10: vibration — train VAE+OCSVM / LSTM-AE on temp-compensated Z24 features, calibrate threshold on damage month, wire BHI
- [ ] H2–H8: pipeline — simulator → Mosquitto → Postgres → live chart working
- [ ] **H8 HARD GATE:** real ESP32 node streaming? If not, cut it (simulator is authoritative)

### Phase 2 · H10–H16 — Twin & integration
- [ ] H10–H16: wire twin to data bus (Section 8 order), crack overlay + amplified deflection, dashboard

### Phase 3 · H16–H24 — Integration & first rehearsal
- [ ] H16–H20: full-stack integration in **replay mode**; end-to-end test of the hero flow
- [ ] H20–H24: first storyboard rehearsal; fix the 3 worst things; **team rest/meal break**

### Phase 4 · H24–H32 — **FEATURE FREEZE** (no new features)
- [ ] H24 HARD GATE: FEATURE FREEZE. Switch to: real metrics (mAP / confusion matrix / RMSE), hardening, backup video recording (2 takes), pitch drafting
- [ ] H28: presenter stops coding; rehearses timed 6-min pitch ≥3× (once to a stranger/mentor); Q&A bank owners finalize
- [ ] H28–H32: 3-tier demo assets (live → video → screenshots) on 2 laptops + 1 phone; live-sensor smoke test

### Phase 5 · H32–H35.5 — Freeze & dry run
- [ ] H32: DEMO FREEZE — if anything is still broken, cut the live sensor path, run 100% on replay (all 4 mandated components remain demonstrable)
- [ ] H34: full 6-min dry run with timer + projector/audio/scaling
- [ ] H35: submit **30 minutes early**, not 30 seconds early
- [ ] H35.5: walk-in bag check (2 laptops, spare batteries, USB-C hub, ethernet adapter)

**Sleep:** 2-shift rotation, ≥4 awake at all times, 4–6h continuous sleep per member, presenter gets 8h the night before demo day, **no all-nighters after H24**.

---

## 12. Pre-hackathon checklist (Day −14 → −1)

### Compliance & logistics (Day −14)
- [ ] Confirm VITISH roster = **6 members incl. ≥1 female**; unique team name **without the institute name**
- [ ] **Email/call organizers:** exact judging scorecard, demo format (live vs PPT), time limit, Q&A length, submission format, any idea-presentation template
- [ ] If no scorecard, assume SIH categories: problem understanding, innovation, technical execution/feasibility, impact, usability, presentation
- [ ] One-paragraph idea description hitting all 4 mandated components + 10-slide idea PPT

### Data & compute (Day −14 → −7)
- [ ] Download Z24 processed mirror (~992 MB) — office WiFi
- [ ] **Register with KU Leuven** for official Z24 .mat (keep the confirmation email — license story in Q&A)
- [ ] Download dacl10k v3 (~1.1 GB) + toolkit
- [ ] Download SDNET2018 (correct slug) + Ultralytics crack-seg
- [ ] Download Vänersborg (optional sanity check)
- [ ] Fetch US NBI coordinates for 50 real bridges
- [ ] Inventory GPU: team laptop(s) with CUDA, or a Colab/Kaggle notebook pre-staged with pinned torch+CUDA
- [ ] Pre-stage a working venv/Docker image with all pinned deps; verify `pip install` offline from cache

### Pre-compute (Day −7 → −3)
- [ ] dacl10k masks → YOLO-seg conversion (crack-only subset)
- [ ] Pre-train baseline binary crack segmenter (~2–4h GPU)
- [ ] Z24 hourly modal-frequency + temperature features → cached .npy
- [ ] Pre-train VAE+OCSVM + LSTM-AE; **verify anomaly rises on damage, flat on temperature-only**
- [ ] Build R3F twin shell with pinned versions + mock-data mode (Section 8, pre-build half)
- [ ] ESP32 firmware: WiFi + MQTT publish + rolling RMS flag — bench-tested
- [ ] Docker Compose (Postgres + EMQX/Mosquitto + app) — one command up
- [ ] Freeze message contract, BHI formula/weights, 6-min storyboard script
- [ ] Build demo-driver replay tool
- [ ] **Copy everything to USB + cloud. Verify it all runs with network OFF.**

### Pitch & Q&A (Day −3 → −1)
- [ ] Write 6-min pitch script draft + 15-second Morbi cold-open hook
- [ ] Lock the death-toll number against a primary source (official ~135 / Wikipedia 141)
- [ ] Build the Q&A bank (§14) with 2 owners; rehearse hostile questions
- [ ] Practice the demo on venue-class hardware; record 2 backup takes

---

## 13. The 6-minute storyboard (facts corrected)

Total: 6:00. Everything shown by minute 2:00.

| Time | Beat | Script (approved wording) |
|---|---|---|
| 0:00–0:15 | **Cold open** | "Morbi, October 30, 2022. A 140-year-old suspension bridge rated for 125 people — carrying 500. Rusted cables. Broken anchors. Loose bolts. 135 lives lost — some tallies say 141. The inspection regime failed." (Do NOT say "4 corroded cables" or "would have prevented".) |
| 0:15–1:00 | **Problem** | "Gujarat after Gambhira: 1,800+ bridges inspected in one state — 20 closed fully, 113 partially. MoRTH is running a nationwide digital survey of 1.7 lakh bridges, deadline 30 Sep 2026. We can't manually inspect our way out — we need continuous monitoring." Global beat: "In the last two years: 52 dead at Meizhou, 38 at Shangluo, 22 at Gambhira, 13 in Brazil." |
| 1:00–2:00 | **The 4 mandated components** | One sentence each — IoT sensors, computer vision, digital twin, predictive maintenance — mapped to the live dashboard on screen. "The government's NBHMS architecture and our stack are the same shape." |
| 2:00–4:00 | **LIVE DEMO** (hero flow) | Real-time: a crack is detected by the vision model → vibration anomaly score rises → BHI drops from 87 → dashboard flags an alert → the digital twin highlights the affected section. **Label every source on screen** ("Z24 benchmark data · 100 Hz", "simulated feed", "LIVE" badge on the real ESP32 stream if it passes smoke test). Show the VAE/OCSVM confusion matrix by scenario. End with the LLM copilot: "Tendon-rupture signature detected — recommend load restriction and strain-gauge verification." |
| 4:00–5:00 | **Impact** | "USD ~$260–300 per bridge per year at scale, vs billions in failure cost. This is the low-cost tier beneath Sydney Harbour's 2,400 sensors." |
| 5:00–5:30 | **Future work** | "Cable strain + acoustic sensing to close the corrosion blind spot. Federated learning across a bridge network without sharing raw data." |
| 5:30–6:00 | **Close** | "This is what the next Morbi looks like — and this is the system that catches it before the news does." |

**Honesty beats — spoken during demo:** "Z24 is a Swiss concrete box-girder bridge; Morbi was a steel suspension footbridge. Nothing transfers directly — Z24 is our proof-of-method, and a production system trains per structure type, then per bridge." "We disclose it plainly: the hero bridge streams the real benchmark through the real pipeline; the 49 other bridges are illustrative — real locations, simulated health." Say **"N days before the final rupture scenario"** with N measured during the build (≈30 or ≈15), never "18".

---

## 14. Q&A defense (12 canned answers + fixes)

### Fixes to the report's existing 20 questions
- **#5:** "dacl10k is naturally balanced" is FALSE (crack dominates; it's multi-label + imbalanced). Say: focal loss + class weights. SDNET2018 IS balanced 50/50.
- **#7:** Reconcile FPR 4% with mean+3σ (theoretical 0.13%): the healthy-error distribution is non-Gaussian.
- **#8:** BHI weights are a *design choice* reflecting evidence reliability (to be re-calibrated on pilot data) — NOT "swept on the Z24 test set" (incoherent: Z24 has no images).
- **#12:** Latency splits into ~200 ms streaming vs ~10.5 s + inference anomaly; pick QoS 1 or 2, not both.
- **#16:** Reconcile $5–15/mo vs $46.7/mo TCO, $500 vs $560/yr, $300 vs $588 hardware (state the MPU6050-class downgrade explicitly).
- **#19:** Replace "would have flagged Morbi weeks early" with the reframe in §13.

### 12 canned answers (the audit's highest-priority gaps)

**Q1 — Temperature shifts frequencies ~9% on Z24 itself (the 1,006-citation paper). How do you separate damage from weather?**
"This is our biggest validated risk. Our 3σ threshold is calibrated on healthy windows spanning a full environmental cycle; we feed temperature-compensated features and log temp/humidity as co-variates (they're in the BOM). We don't claim environmental robustness was proven in 36 hours — de-confounding is the pilot's first validation task."

**Q2 — Prove your system would have prevented Morbi. Where is the Morbi data?**
"We never claim validated prevention — Morbi had no sensors, so it cannot be a test set. What Z24 proves is that our detector flags documented progressive damage ~N days before the final rupture scenario. Morbi is our motivation; its mode — cable-anchorage corrosion under overload — is a known blind spot of global-vibration monitoring, which is why our roadmap adds cable-strain and acoustic sensing."

**Q3 — FPR 4% means 2 of 50 bridges are always red (alarm fatigue). What's your miss rate on EARLY damage like the 2 cm settlement?**
"We'll show the full confusion matrix by Z24 scenario, not one F1. Honest weakness: early subtle stages — we reliably catch settlement ≥4 cm, spalling, tendon rupture; the 2 cm stage may sit inside the healthy envelope. A miss is fatal, a false alarm only costs inspection time, so we weight visual evidence higher, require confirmation before any closure recommendation, and track early-stage sensitivity as a documented pilot metric."

**Q4 — Z24 needs a signed KU Leuven research agreement (non-commercial, no third-party transfer). Did you sign it? Is that HuggingFace copy authorized?**
"We hold the data under the KU Leuven research license for evaluation, using the official .mat files; we did not rely on third-party redistributions for validation. The research license excludes commercial use — that's why the pilot deploys sensors on a partner PWD bridge and transitions to self-captured data."

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

**Q12 — Is the demo real or pre-recorded? (integrity)**
Everything is live from the local stack. We recorded a backup video and have screenshots as contingency — but the demo you're watching is the real pipeline: the MQTT broker is local, the models run here, and the data source is labeled on screen. The git history shows the build hour by hour."

**Standing rule:** never claim a number or feature stronger than what's in the repo. Honesty reads as confidence.

---

## 15. Risk register (from both audits)

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | dacl10k toolchain + imbalance eats the CV phase | Very high | High | Binary SDNET2018 segmenter in the 36h; dacl10k pre-trained baseline; masks pre-converted |
| 2 | Thermal false alarms destroy predictive-maintenance credibility | High | High | Temperature-compensated features; threshold on full ambient year; pre-validate damage-up/flat-weather |
| 3 | Live hardware chain dies at demo (WiFi/battery/sensor/MQTT) | High | High | Replay-first demo; local broker; pre-bench-tested firmware; spare parts; H8 cut rule |
| 4 | Integration spiral in the final 12h | High | Critical | Message contract + BHI formula frozen Day 0; pre-built twin shell + pinned versions; Docker Compose one-command; thin glue first |
| 5 | GPU/environment failure | Medium | Critical | Pre-inventory GPU; pre-staged venv/Docker/Colab with pinned torch+CUDA; pre-cached data + weights on USB; small models (yolov8s-seg) |
| 6 | Judge probes "18 days before failure" / "would have flagged Morbi" | High | High/Critical | Reframe (§13); measure real N; disclose limits |
| 7 | Accuracy claims unsupported | Medium-High | High | Report measured mAP / full confusion matrix; state window + threshold definitions |
| 8 | Z24 licensing question | Medium | Medium | Actually register with KU Leuven; keep confirmation; disclose non-commercial terms |
| 9 | "Live vs simulated" credibility | High | Medium | Label every source on screen; pre-rehearsed disclosure |
| 10 | Cost-math inconsistency | Medium | Medium | Use corrected tables (§16) |
| 11 | Fact-check trivia (tolls, citations, "60 m", "4 cables") | Low-Med | Low | Bulk corrections in §3.2 |
| 12 | drei Text font CDN / map tiles offline | Medium | Medium | HTML overlays; prewarm tiles; SVG fallback |
| 13 | Venue WiFi dependence | High | High | Fully local stack; ethernet adapter; 3-tier demo |

---

## 16. Cost / BOM (corrected)

### Pilot (10 nodes, one bridge)
| Line | Cost |
|---|---|
| 10× ESP32-S3 (~$10 ea) | ~$100 |
| 10× ADXL355 breakout/eval (~$30–57 ea) | ~$300–570 |
| 4× Pi camera nodes ($40 ea) | ~$160 |
| Solar + enclosure + misc | ~$250 |
| **Pilot total** | **~$810–1,080** |

### Scaled (per bridge/year, at 1,000+ bridges)
| Line | Cost |
|---|---|
| Hardware amortized (MPU6050-class downgrade stated explicitly) | ~$50 |
| Cloud (MQTT broker, DB, inference) | ~$60 |
| Shared drone inspection amortized | ~$150 |
| **Recurring all-in TCO** | **~$260/bridge/yr** (≈$21.7/mo) |
| **Recommended SaaS price** | **$25–30/bridge/mo** (above TCO) |

Do not print $560, $300, $5–15/mo, or $10–50/mo anywhere.

---

## 17. Post-hackathon roadmap

- **Months 1–2:** partner PWD bridge pilot (10 nodes); self-captured data; BHI calibration vs IBMS CRN 0–6; environmental de-confounding study.
- **Months 3–6:** per-structure-type retraining; strain + acoustic sensor integration (closes the corrosion blind spot); federated learning across the pilot network; IBMS digital-survey integration.
- **If SIH is a feeder:** reuse the same pitch/demo as the template for the national portal + finale. Collect the VITISH scorecard feedback and fix the lowest category first.
- **Commercial:** honor CC BY-NC 4.0 (dacl10k) and the KU Leuven research license — product data must be licensed or self-captured.

---

## 18. Source register (key links)

**Data:** HF Z24 mirrors (`thanglexuan/Z24-dataset-processed`, `Sagarr123/Z24-dataset-processed`) · KU Leuven Z24 portal · dacl10k (arXiv:2309.00460, `phiyodr/dacl10k-toolkit`) · SDNET2018 (IEEE DataPort correct slug) · Ultralytics crack-seg · Vänersborg Zenodo 8300495 · US NBI (FHWA)
**Policy:** MoRTH IBMS circular (25 Jun 2026) · IIT-M/C-DAC NBHMS MoU (9 Jul 2026) · ISHMS Guidelines v1 (16 Jul 2025) · NHAI Teesta/Mahananda BHMS tender
**SOTA:** Benfenati et al. arXiv:2404.02944 (IEEE TSUSC 2025) · Neumann et al. arXiv:2409.17735 · Sajedi & Liang arXiv:2004.05151 · CiF arXiv:2605.18413 · SECrackSeg (Sensors 2025) · SHM-Agents arXiv:2605.12916 · SPECTRA arXiv:2607.03446 · Torzoni et al. arXiv:2506.14453 · Zhang & Liang arXiv:2512.18780 · Feng et al. arXiv:2606.03084 · Phan et al. arXiv:2411.04475 · VAE+OCSVM Z24 (Scientific Reports 2025)
**Failures/market:** Wikipedia Morbi / Gambhira / List of bridge failures · ASCE 2025 Report Card · ARTBA 2025 Bridge Report · Business Research Company SHM market report
**Twin:** npm registry (all pinned versions) · R3F releases v9.5.0/v9.7.0 · MapLibre CHANGELOG · OpenFreeMap
**Competitors:** resensys.com · sensr.com · developer.bentley.com/pricing · campbellsci.com/bridge-monitoring · encardio.com / proqio.com · movesolutions.it · senceive.com · sensequake.com · spplindia.org · hbkworld.com
**Playbook:** SIH 2026 Guidelines PDF (sih.gov.in) · HackerEarth / JetBrains / Devpost judging guides
**Open source:** PySHM · pyOMA2 · OpenBDLM · esp-tflite-micro · dacl10k-toolkit · Elios-Lab Z24
