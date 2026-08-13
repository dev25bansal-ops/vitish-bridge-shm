---
tags: [home, vitish-2026, shm]
---

# 🏗️ VITISH 2026 · PS#99 — AI-Based Structural Health Monitoring for Bridges

> **Mission:** Prevent the next Morbi. IoT sensors + computer vision + digital twin + predictive maintenance, fused into one auditable Bridge Health Index — the low-cost tier of the Government's NBHMS architecture.

**Build window:** 36 hours · **Team:** 6 · **Demo:** 6 minutes

## Quick navigation

- 📋 [[Mission]] · [[Four-Components]] · [[Team]] · [[Key-Decisions]]
- 🔬 [[Verified-Facts]] · [[Datasets]] · [[Academic-SOTA]] · [[India-Policy]]
- 🏛️ [[System-Architecture]] · [[Message-Contract]] · [[BHI-Formula]] · [[Tech-Stack]]
- 🔨 [[Build-Log]] · [[Data-Pipeline]] · [[CV-Model]] · [[Vibration-Model]] · [[Digital-Twin]]
- 🎤 [[Storyboard]] · [[QandA-Prep]] · [[Metrics]]
- ⚠️ [[Risk-Register]] · ✅ [[Pre-Hackathon-Checklist]] · [[36h-Build-Plan]]

## The pitch hook (one line)

> "MoRTH's IBMS nationwide digital survey (~1.7 lakh NH bridges, deadline **30 Sep 2026**) plus the IIT Madras / C-DAC **NBHMS** is a 1:1 match to our stack. We're the open, low-cost reference implementation."

## The 10 decisions (full rationale in [[Key-Decisions]])

| # | Decision |
|---|---|
| 1 | **Simulator-first, live-second** — replay Z24 through the real pipeline; one ESP32 is a stretch goal |
| 2 | **Binary crack segmentation on SDNET2018** in the 36h; dacl10k is pre-hackathon only |
| 3 | **YOLO26s-seg** (Jan 2026), not YOLOv8 |
| 4 | **VAE+OCSVM** primary vibration model; LSTM-AE edge baseline; MiniRocket fallback |
| 5 | **Temperature-compensated** Z24 features (thermal false alarms are trap #1) |
| 6 | **Transparent BHI** — 3 sub-indices + uncertainty band, not a black box |
| 7 | **Pre-built twin shell**, pinned versions (R3F ^9.7 + React 19.2 + three 0.185) |
| 8 | **Reframed Morbi claim** — motivation, not validation (overload+corrosion is a blind spot) |
| 9 | **Corrected cost math** — ~$260/bridge/yr scaled, $25–30/mo SaaS |
| 10 | **Corrected facts** — Morbi 135 (some tallies 141), suspension bridge, drop "18 days" |

## Live status

- ✅ Research (12-agent workflow) complete
- ✅ Master build plan written
- ✅ **Build + integration verified** — see [[Build-Log]]
- 🔜 Demo rehearsal + stretch training

---

*Built from the full research report + a 12-agent global research workflow (10 research agents + 2 adversarial audits), all sources fetched live 13 Aug 2026.*
