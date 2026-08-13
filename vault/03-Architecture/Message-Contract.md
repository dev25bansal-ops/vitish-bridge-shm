---
tags: [architecture, contract, vitish-2026, shm]
created: 2026-08-13
---

# Message Contract (frozen — Day 0)

Freeze this BEFORE any coding. Every producer/consumer implements it verbatim.

## Topics

| Topic | Rate | QoS |
|---|---|---|
| `bridge/{id}/accel` | 1 msg/s/node | 1 |
| `bridge/{id}/flag` | event | 2 (alarm) |
| `bridge/{id}/frame` | ~1/beat | 1 |
| `bridge/{id}/bhi` | 1 msg/s | 1 |
| `bridge/span-7/rf` | simulated | 1 (LoRa backhaul prop) |

**QoS decision (fixed):** QoS 1 for telemetry, **QoS 2 for alarms**. The old report said both 1 and 2 — this is the one ([[Verified-Facts]] #9).

## JSON schemas

```json
// bridge/sensor-07/accel  (1 msg/s)
{
  "bridge": "z24",
  "node": 7,
  "ts": 1786123456,
  "fs": 100,
  "samples": [0.012, "…100 floats"],
  "rms": 0.083,
  "flag": 0
}

// bridge/z24/bhi  (1 msg/s)
{
  "bridge": "z24",
  "ts": 1786123457,
  "bhi": 82.4,
  "u": 3.1,
  "cv": 0.35,
  "vib": 0.12,
  "load": 0.4,
  "state": "GREEN"
}
```

## Windowing

- **10.24 s anomaly window = 1024 samples @ 100 Hz** → anomaly detection is ~10.5 s + inference, NOT 200 ms.
- 200 ms is streaming-telemetry latency only (10 + 30 + 50 + 100 = 190 ms defensible). State both ([[Metrics]]).
- 60-s Z24 recordings = 10 × 6000-sample segments ([[Z24-Benchmark]]).

## Rules

- Batched 100-sample payloads per node.
- `ts` epoch seconds; `fs` always 100; `flag` = rolling-RMS anomaly bit from the edge.
- Simulator adds ~5% amplitude jitter + occasional packet drop for robustness ([[Data-Pipeline]]).

Related: [[System-Architecture]] · [[BHI-Formula]] · [[Data-Pipeline]]
