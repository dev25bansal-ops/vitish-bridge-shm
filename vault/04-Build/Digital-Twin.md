---
tags: [build, twin, vitish-2026, shm]
created: 2026-08-13
---

# Digital Twin — pre-built shell, wired in 8 h

Component 3 of 4. The shell is built BEFORE H0; the 8-hour budget inside the 36 h is **wiring only** ([[Pre-Hackathon-Checklist]]).

## Architecture rules

- **Parametric Morbi-style suspension bridge from primitives** (<10k tris) — NOT a downloaded GLB (can't rig a static model for collapse replay).
- One `<InstancedMesh>` for all sensors = **1 draw call**.
- Browser-native **WebSocket** (no lib) → **zustand store** ← broker.
- drei `Html` popups + **Recharts** spectrum (256-pt window).
- **MapLibre GL 6** (~60-line wrapper) + OpenFreeMap 50-bridge regulator view (real US NBI locations, simulated BHI) — not react-map-gl, **no Cesium**.
- **SVG-map fallback** if tiles are offline; prewarm/cache tiles at the venue.

## Pinned versions

`react ^19.2.8` · `three ^0.185.1` · `@react-three/fiber ^9.7.0` · `@react-three/drei ^10.7.8` · `zustand ^5.0.14` · `recharts ^3.10.1` · `maplibre-gl ^6.3.0` · `@types/three ^0.185.4` (full tree in [[Tech-Stack]]).

## During the 36 h (strict order, 8 h)

| Time | Task |
|---|---|
| 0:00–0:30 | Verify shell runs in venue env; `npm run build && vite preview` |
| 0:30–1:30 | Wire WebSocket → zustand → mock data (offline-safe) |
| 1:30–3:00 | Live bindings: 2 modal frequencies, temperature, BHI with **amplified deflection (~100×)** |
| 3:00–4:30 | instancedMesh sensor markers + raycast click + Html popup + Recharts spectrum |
| 4:30–6:00 | MapLibre 50-bridge map + selection sync |
| 6:00–7:00 | Storyboard scenes: cable break, deck sag, **BHI 87 → 12 sensor cascade** |
| 7:00–8:00 | Perf pass (`dpr={[1,1.5]}`, shadows off, memo popups) + **network-off test** |

## Store / WS

- `zustand` store holds `bhi`, `u`, `vib`, `cv`, `load`, node RMS + flag, selected bridge.
- WS receives `bridge/{id}/bhi` + `flag` ([[Message-Contract]]).
- **Offline fixture generator** persists a fake stream for the network-off demo.

## Copilot pane

- LLM pane (SHM-Agents style): alert → plain-language maintenance recommendation. Mock with a local LLM or canned templates.

Related: [[Tech-Stack]] · [[System-Architecture]] · [[Storyboard]] · [[Data-Pipeline]]
