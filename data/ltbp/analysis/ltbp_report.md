# LTBP / InfoBridge — empirical deterioration + Markov priors

_44 LTBP pilot bridges (real longitudinal 1993-2025) + 1892 bridge fleet cross-section, from FHWA InfoBridge Selected-Bridges exports (2026-08-14). Regenerate: `python scripts/ltbp_analyze.py`._

> ⚠️ **Data quirk:** this export's `58 - Deck Condition Rating` is a saturated 0/1 field (constant within every bridge) — **not** the real NBI deck rating. We use **super (59)** and **sub (60)** only.

## Fleet snapshot (cross-sectional)

- Bridges: **1892** · mean age **35.21 yr** · freeze-thaw **73.54/yr** · mean temp **21.64 °C**
- Mean superstructure: **6.43** · substructure: **6.88** (NBI 0-9)
- Mean ADT: **16,996.35**

### CAT10 current condition

| Condition | # bridges |
|---|---|
| Fair | 951 |
| Good | 829 |
| Poor | 53 |

## Cross-sectional condition vs age (fleet, NBI 0-9)

Different bridges at different ages — a fleet prior, NOT longitudinal RUL. | age | n | super | sub |

| Age | n | super (mean) | sub (mean) |
|---|---|---|---|
| 1 | 6 | 7.5 | 8.0 |
| 2 | 5 | 8.6 | 8.6 |
| 3 | 9 | 7.667 | 8.222 |
| 4 | 7 | 6.857 | 7.714 |
| 5 | 20 | 7.55 | 8.0 |
| 6 | 3 | 8.0 | 8.0 |
| 7 | 6 | 7.5 | 7.667 |
| 8 | 5 | 7.4 | 7.4 |
| 9 | 13 | 7.538 | 7.846 |
| 10 | 7 | 7.429 | 8.0 |
| 11 | 8 | 7.125 | 8.0 |
| 12 | 13 | 7.385 | 7.692 |
| 13 | 4 | 7.5 | 7.75 |
| 14 | 9 | 7.111 | 7.444 |
| 15 | 38 | 6.974 | 7.684 |
| 16 | 37 | 7.054 | 7.432 |
| 17 | 35 | 7.143 | 7.543 |
| 18 | 51 | 6.922 | 7.451 |
| 19 | 43 | 7.163 | 7.581 |
| 20 | 39 | 7.051 | 7.41 |
| 21 | 43 | 6.953 | 7.279 |
| 22 | 37 | 6.919 | 7.243 |
| 23 | 37 | 6.703 | 7.243 |
| 24 | 43 | 6.93 | 7.163 |
| 25 | 31 | 6.806 | 7.194 |
| 26 | 39 | 6.667 | 7.077 |
| 27 | 48 | 6.729 | 7.271 |
| 28 | 42 | 6.952 | 7.167 |
| 29 | 46 | 6.739 | 7.217 |
| 30 | 36 | 6.889 | 7.278 |
| 31 | 25 | 6.68 | 7.08 |
| 32 | 28 | 6.429 | 6.821 |
| 33 | 48 | 6.5 | 6.938 |
| 34 | 30 | 6.833 | 7.1 |
| 35 | 40 | 6.6 | 6.9 |
| 36 | 31 | 6.129 | 6.677 |
| 37 | 49 | 6.653 | 6.633 |
| 38 | 44 | 6.659 | 6.841 |
| 39 | 40 | 6.45 | 6.675 |
| 40 | 54 | 6.389 | 6.833 |
| 41 | 45 | 6.133 | 6.556 |
| 42 | 26 | 6.346 | 6.731 |
| 43 | 36 | 6.361 | 6.722 |
| 44 | 37 | 6.27 | 6.541 |
| 45 | 35 | 6.314 | 6.657 |
| 46 | 31 | 6.419 | 6.419 |
| 47 | 24 | 6.292 | 6.375 |
| 48 | 34 | 6.471 | 6.882 |
| 49 | 37 | 6.432 | 6.622 |
| 50 | 31 | 5.935 | 6.29 |
| 51 | 13 | 6.154 | 6.231 |
| 52 | 44 | 6.227 | 6.409 |
| 53 | 20 | 5.1 | 6.3 |
| 54 | 29 | 6.0 | 6.0 |
| 55 | 22 | 5.727 | 6.409 |
| 56 | 42 | 6.31 | 6.429 |
| 57 | 40 | 6.225 | 6.35 |
| 58 | 22 | 6.318 | 6.773 |
| 59 | 19 | 6.158 | 6.474 |
| 60 | 25 | 6.28 | 6.24 |
| 61 | 15 | 6.6 | 6.0 |
| 62 | 22 | 6.045 | 5.955 |
| 63 | 17 | 6.471 | 6.118 |
| 64 | 16 | 6.0 | 6.0 |
| 87 | 1 | 7.0 | 8.0 |
| 97 | 1 | 7.0 | 7.0 |

## Markov transition probabilities — super, deterioration-only (pilot 44 bridges)

Row = current state; columns = stay-same / degrade-1. 35 pilot bridges showed at least one change. Small-sample empirical prior — label as such alongside literature values.

| from | n | stay same | degrade 1 |
|---|---|---|---|
| 0 | 2 | 1.000 | 0.000 |
| 1 | 22 | 0.909 | 0.091 |
| 3 | 3 | 1.000 | 0.000 |
| 4 | 9 | 0.889 | 0.111 |
| 5 | 78 | 0.974 | 0.026 |
| 6 | 215 | 0.981 | 0.019 |
| 7 | 515 | 0.959 | 0.037 |
| 8 | 230 | 0.887 | 0.104 |
| 9 | 8 | 0.375 | 0.625 |

## Markov transition probabilities — sub, deterioration-only (pilot 44 bridges)

Row = current state; columns = stay-same / degrade-1. 34 pilot bridges showed at least one change. Small-sample empirical prior — label as such alongside literature values.

| from | n | stay same | degrade 1 |
|---|---|---|---|
| 4 | 7 | 1.000 | 0.000 |
| 5 | 162 | 0.994 | 0.006 |
| 6 | 190 | 0.947 | 0.053 |
| 7 | 323 | 0.947 | 0.050 |
| 8 | 400 | 0.932 | 0.065 |
| 9 | 11 | 0.545 | 0.364 |

_Source: FHWA InfoBridge / Long-Term Bridge Performance (LTBP). US federal open data._