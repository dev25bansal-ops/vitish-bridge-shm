---
tags: [demo, storyboard, vitish-2026, shm]
created: 2026-08-13
---

# The 6-Minute Storyboard (facts corrected)

Total 6:00. **Everything shown by minute 2:00.** All wording approved — do not improvise numbers.

| Time | Beat | Script (approved wording) |
|---|---|---|
| 0:00–0:15 | **Cold open** | "Morbi, October 30, 2022. A 140-year-old suspension bridge rated for 125 people — carrying 500. Rusted cables. Broken anchors. Loose bolts. 135 lives lost — some tallies say 141. The inspection regime failed." (Do NOT say "4 corroded cables" or "would have prevented".) |
| 0:15–1:00 | **Problem** | "Gujarat after Gambhira: 1,800+ bridges inspected in one state — 20 closed fully, 113 partially. MoRTH is running a nationwide digital survey of 1.7 lakh bridges, deadline 30 Sep 2026. We can't manually inspect our way out — we need continuous monitoring." Global beat: "In the last two years: 52 dead at Meizhou, 38 at Shangluo, 22 at Gambhira, 13 in Brazil." |
| 1:00–2:00 | **The 4 mandated components** | One sentence each — IoT sensors, computer vision, digital twin, predictive maintenance — mapped to the live dashboard on screen. "The government's NBHMS architecture and our stack are the same shape." ([[Four-Components]]) |
| 2:00–4:00 | **LIVE DEMO (hero flow)** | Real-time: a crack is detected by the vision model → vibration anomaly score rises → BHI drops from 87 → dashboard flags an alert → the digital twin highlights the affected section. **Label every source on screen** ("Z24 benchmark data · 100 Hz", "simulated feed", "LIVE" badge on the real ESP32 stream if it passes smoke test). Show the VAE/OCSVM confusion matrix by scenario. End with the LLM copilot: "Tendon-rupture signature detected — recommend load restriction and strain-gauge verification." |
| 4:00–5:00 | **Impact** | "USD ~$260–300 per bridge per year at scale, vs billions in failure cost. This is the low-cost tier beneath Sydney Harbour's 2,400 sensors." ([[Metrics]]) |
| 5:00–5:30 | **Future work** | "Cable strain + acoustic sensing to close the corrosion blind spot. Federated learning across a bridge network without sharing raw data." |
| 5:30–6:00 | **Close** | "This is what the next Morbi looks like — and this is the system that catches it before the news does." |

## Verified demo numbers (measured 2026-08-13, real Z24 replay)

So the presenter is never surprised by the live gauge:

- **Healthy phase**: BHI starts **87** (fusion initial state) then settles **73–79 GREEN** on real Z24 (vib 0.12–0.20) — "strong, healthy bridge" is honest.
- **80 s**: rupture onset detected → **AMBER 68** (vib 0.43).
- **90 s**: crosses into **RED 49** (vib ~0.98).
- **110 s**: bhi-drop beat (load 0.40, cv 0.55) → **RED 33.6**; holds RED through 175 s.
- Alerts fire at 45 s (crack warning), 75 s (vibration warning), 110 s (BHI RED critical), 140 s (tendon-rupture critical).

So "BHI drops from 87" (0:00 baseline) is literally true on the live dashboard, and the 2:00–4:00 demo window shows the full GREEN→AMBER→RED arc. The 49 other bridges in the fleet map remain illustrative (real locations, simulated health) — spoken honestly per the honesty beats.

## Honesty beats — spoken during the demo

- "Z24 is a Swiss concrete box-girder bridge; Morbi was a steel suspension footbridge. **Nothing transfers directly** — Z24 is our proof-of-method, and a production system trains per structure type, then per bridge."
- "We disclose it plainly: the hero bridge streams the real benchmark through the real pipeline; the 49 other bridges are illustrative — real locations, simulated health."
- Say **"N days before the final rupture scenario"** with N measured during the build (≈30 or ≈15), never "18".

## The Morbi reframe (the kill-shot fix)

- Old claim: "would have flagged Morbi weeks early" / "one click could have prevented Morbi."
- New framing: "**Z24 proves we catch documented progressive failure N days early. Morbi is our motivation — and its mode (overload + cable-anchorage corrosion) is a known blind spot of global-vibration monitoring, which is why our roadmap adds strain/acoustic sensing.**"
- Why: Morbi had no sensors → untestable as validation; structurally the opposite of Z24's induced damage. See [[Verified-Facts]] and [[QandA-Prep]] Q2.

## Delivery rules

- Timer + projector/audio/scaling in the full dry run at H34 ([[36h-Build-Plan]]).
- 3-tier demo assets: live → video → screenshots on 2 laptops + 1 phone.
- 15-second Morbi cold-open hook locked; death toll sourced (official ~135 / Wikipedia 141).

Related: [[Mission]] · [[QandA-Prep]] · [[Metrics]] · [[Four-Components]]
