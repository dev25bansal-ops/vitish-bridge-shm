# Per-scenario confusion matrix (Z24 benchmark)

Healthy reference labels [0, 1, 2] (*chronology-inferred*). Threshold mean+3σ = 0.9368.

                      predicted
                    anomaly   normal
  actually damage         10     6290
  actually healthy         9     1341
precision 0.5263 · recall 0.0016 · F1 0.0032

## Per-scenario detection (flag = score > 0.35)
| label | scenario | n | median | p90 | flag frac |
|---|---|---|---|---|---|
| L0 | reference / undamaged | 450 | 0.1598 | 0.5309 | 0.2356 |
| L1 | undamaged | 450 | 0.247 | 0.6321 | 0.3067 |
| L2 | undamaged | 450 | 0.245 | 0.6391 | 0.3289 |
| L3 | pier settlement 20 mm | 450 | 0.1936 | 0.6605 | 0.2711 |
| L4 | pier settlement 40 mm | 450 | 0.2722 | 0.7662 | 0.44 |
| L5 | pier settlement 80 mm | 450 | 0.2067 | 0.6011 | 0.2911 |
| L6 | pier settlement 95 mm | 450 | 0.2009 | 0.5291 | 0.2578 |
| L7 | concrete spalling | 450 | 0.2208 | 0.714 | 0.3444 |
| L8 | hinge failure | 450 | 0.1835 | 0.5218 | 0.2489 |
| L9 | anchor-head failure | 450 | 0.2302 | 0.5872 | 0.3022 |
| L10 | tendon rupture | 450 | 0.1713 | 0.4441 | 0.1956 |
| L11 | post-repair (1) | 450 | 0.216 | 0.5556 | 0.2778 |
| L12 | post-repair (2) | 450 | 0.1624 | 0.4231 | 0.1533 |
| L13 | post-repair (3) | 450 | 0.1876 | 0.4555 | 0.1956 |
| L14 | reference | 450 | 0.1778 | 0.4279 | 0.1733 |
| L15 | reference | 450 | 0.2415 | 0.6131 | 0.3244 |
| L16 | reference | 450 | 0.1794 | 0.4903 | 0.2467 |

Honesty note: scenario names follow the Z24 campaign chronology but the processed mirror omits a label legend — treat names as inferred until verified against the registered KU Leuven portal metadata.