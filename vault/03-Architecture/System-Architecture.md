---
tags: [architecture, vitish-2026, shm]
created: 2026-08-13
---

# System Architecture (frozen)

4 layers, one hero demo path. Frozen on Day 0 before any coding ([[Message-Contract]]).

## The 4 layers

```mermaid
flowchart TB
    subgraph L1["Layer 1 · Edge / Sensing"]
        SIM["Z24 replay simulator<br/>(nodes 6-8 of 27 · 100 Hz)<br/>damage injector + jitter"]
        ESP["ESP32-S3 + ADXL355<br/>(stretch goal, rolling RMS flag)"]
        CAM["Pi Zero 2 W camera prop<br/>(stream-only JPEG)"]
    end
    subgraph L2["Layer 2 · Communication"]
        MQTT["Mosquitto broker<br/>LOCAL on demo laptop"]
    end
    subgraph L3["Layer 3 · AI Processing"]
        CV["CV: YOLO26s-seg binary crack<br/>(fallback YOLO11s) + SAM2 opt"]
        VIB["Vibration: VAE+OCSVM primary<br/>LSTM-AE edge · MiniRocket fallback<br/>→ anomaly + uncertainty"]
        FUS["Fusion: BHI = f(crack, vib, load)<br/>transparent weights + band"]
    end
    subgraph L4["Layer 4 · Twin & Dashboard"]
        TWIN["React Three Fiber parametric bridge<br/>instancedMesh sensors · collapse replay"]
        MAP["MapLibre GL 6 · 50-bridge regulator view"]
        COP["LLM copilot pane → maintenance advice"]
    end
    L1 -->|"MQTT bridge/{id}/accel + flag + frame"| L2
    L2 --> L3
    L3 -->|"BHI 1 msg/s"| L2
    L2 -->|"WebSocket"| L4
```

## Message flow (hero path)

`simulator (1 msg/s/node) → MQTT → Postgres (persist) + WS bridge → models (cv + vibration) → fusion/BHI → twin + dashboard`

- Telemetry: ~6–8 msgs/s total (batched 100-sample JSON, 1 msg/s/node).
- QoS: telemetry 1, alarms 2 ([[Message-Contract]]).

## Replay-first principle

1. **Replay is authoritative** — all four subsystems consume a recorded Z24 replay through the real MQTT → DB → inference → twin pipeline.
2. The live ESP32 node is a garnish, shown only if a pre-demo smoke test passes (H8 cut rule, [[36h-Build-Plan]]).
3. Every screen source is **labeled** ("Z24 · 100 Hz", "simulated feed", "LIVE") — kills the integrity question ([[Storyboard]], [[QandA-Prep]] Q6/Q12).
4. Zero venue-WiFi dependence: local broker, offline fixtures ([[Digital-Twin]]).

Related: [[Four-Components]] · [[Message-Contract]] · [[Data-Pipeline]] · [[Tech-Stack]]
