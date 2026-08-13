---
tags: [risk, vitish-2026, shm]
created: 2026-08-13
---

# Risk Register (13 rows, from both audits)

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | dacl10k toolchain + imbalance eats the CV phase | Very high | High | Binary SDNET2018 segmenter in the 36h; dacl10k pre-trained baseline; masks pre-converted |
| 2 | Thermal false alarms destroy predictive-maintenance credibility | High | High | Temperature-compensated features; threshold on full ambient year; pre-validate damage-up/flat-weather |
| 3 | Live hardware chain dies at demo (WiFi/battery/sensor/MQTT) | High | High | Replay-first demo; local broker; pre-bench-tested firmware; spare parts; H8 cut rule |
| 4 | Integration spiral in the final 12h | High | Critical | Message contract + BHI formula frozen Day 0; pre-built twin shell + pinned versions; Docker Compose one-command; thin glue first |
| 5 | GPU/environment failure | Medium | Critical | Pre-inventory GPU; pre-staged venv/Docker/Colab with pinned torch+CUDA; pre-cached data + weights on USB; small models (yolov8s-seg) |
| 6 | Judge probes "18 days before failure" / "would have flagged Morbi" | High | High/Critical | Reframe ([[Storyboard]]); measure real N; disclose limits |
| 7 | Accuracy claims unsupported | Medium-High | High | Report measured mAP / full confusion matrix; state window + threshold definitions |
| 8 | Z24 licensing question | Medium | Medium | Actually register with KU Leuven; keep confirmation; disclose non-commercial terms |
| 9 | "Live vs simulated" credibility | High | Medium | Label every source on screen; pre-rehearsed disclosure |
| 10 | Cost-math inconsistency | Medium | Medium | Use corrected tables ([[Metrics]]) |
| 11 | Fact-check trivia (tolls, citations, "60 m", "4 cables") | Low-Med | Low | Bulk corrections in [[Verified-Facts]] |
| 12 | drei Text font CDN / map tiles offline | Medium | Medium | HTML overlays; prewarm tiles; SVG fallback ([[Digital-Twin]]) |
| 13 | Venue WiFi dependence | High | High | Fully local stack; ethernet adapter; 3-tier demo |

Top-4 critical (order of attack): 4, 5, 1, 2 — all pre-buildable before H0 ([[Pre-Hackathon-Checklist]]).

Related: [[Key-Decisions]] · [[36h-Build-Plan]] · [[QandA-Prep]]
