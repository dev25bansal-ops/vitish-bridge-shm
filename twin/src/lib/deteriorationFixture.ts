// D2-11 offline mirror — the LTBP Markov projection computed client-side from
// the SAME empirical transition priors the backend uses, so the offline replay
// paints a real curve instead of a permanent "backend unreachable" hole.
//
// Honesty rules for this file:
//   * The transition counts are embedded verbatim from
//     data/ltbp/analysis/ltbp_summary.json (44 FHWA InfoBridge pilot bridges,
//     1993-2025, "super" rating) — regenerate by re-copying from that file.
//   * The algorithm is a line-for-line mirror of backend/app/deterioration.py
//     (transition_matrix -> project -> next_inspection), including the
//     small-n identity fallback for rows with < 5 observed transitions.
//   * The LIVE backend payload always wins over this fixture: the poller in
//     lib/deterioration.ts seeds the fixture once, then overwrites it on the
//     first successful fetch, and re-anchors the fixture to the live BHI on
//     every failed poll so the offline curve still tracks the story.
import type { DeteriorationRow, DeteriorationState } from '../store'

/** Embedded "super"-rating transition COUNTS (not probabilities) — verbatim
 * from data/ltbp/analysis/ltbp_summary.json -> markov_transitions_pilot_only. */
const SUPER_COUNTS: Readonly<Record<string, number>> = {
  '0->0': 2, '0->5': 2,
  '1->0': 2, '1->1': 20, '1->9': 1,
  '3->3': 3, '3->9': 1,
  '4->3': 1, '4->4': 8, '4->8': 1,
  '5->4': 2, '5->5': 76, '5->6': 2, '5->7': 1,
  '6->5': 4, '6->6': 211, '6->7': 6, '6->8': 3,
  '7->5': 2, '7->6': 19, '7->7': 494, '7->8': 6,
  '8->1': 2, '8->7': 24, '8->8': 204,
  '9->8': 5, '9->9': 3,
}

const PRIORS_LABEL_OFFLINE =
  'replay fixture · embedded LTBP priors (44 FHWA InfoBridge pilot bridges, 1993-2025)'

const NOTE_OFFLINE =
  'offline fixture mirror of the live Markov projection — same empirical ' +
  'transition priors, re-anchored to the live BHI. The live LTBP model data ' +
  'replaces this when the backend is reachable; not a certified RUL.'

const NEXT_RULE = 'first year P(NBI <= 4) >= 25%'

/** Mirror of backend deterioration.condition_from_bhi (MODEL ASSUMPTION). */
export function conditionFromBhi(bhi: number): number {
  if (!Number.isFinite(bhi)) return 8
  const nbi = 1.0 + 8.0 * Math.max(0, Math.min(100, bhi)) / 100.0
  return Math.round(nbi)
}

/** Build the 10x10 row-stochastic transition matrix from the embedded counts,
 * with the backend's small-n rule: rows with < 5 observed transitions default
 * to "stay" (identity). */
function transitionMatrix(): number[][] {
  const P: number[][] = Array.from({ length: 10 }, () => Array(10).fill(0))
  for (const [key, c] of Object.entries(SUPER_COUNTS)) {
    const m = /^(\d+)->(\d+)$/.exec(key)
    if (!m) continue
    const i = Number(m[1])
    const j = Number(m[2])
    if (i >= 0 && i < 10 && j >= 0 && j < 10) P[i][j] += c
  }
  for (let i = 0; i < 10; i++) {
    const total = P[i].reduce((a, b) => a + b, 0)
    if (total < 5.0) {
      P[i] = Array(10).fill(0)
      P[i][i] = 1.0
    } else {
      for (let j = 0; j < 10; j++) P[i][j] /= total
    }
  }
  return P
}

/** Mirror of backend _percentiles (NumPy searchsorted side="left"). */
function percentiles(dist: number[], qs: readonly [number, number]): [number, number] {
  const out: [number, number] = [0, 0]
  for (let q = 0; q < qs.length; q++) {
    let cdf = 0
    let idx = 10
    for (let k = 0; k < 10; k++) {
      cdf += dist[k]
      if (cdf >= qs[q]) {
        idx = k
        break
      }
    }
    out[q] = Math.min(9, Math.max(0, idx))
  }
  return out
}

/** Mirror of backend deterioration.project (years 1..N). */
export function project(
  current: number,
  years: number,
  threshold = 4,
): DeteriorationRow[] {
  const P = transitionMatrix()
  let dist = Array(10).fill(0)
  dist[Math.min(9, Math.max(0, Math.round(current)))] = 1.0
  const rows: DeteriorationRow[] = []
  for (let y = 1; y <= years; y++) {
    const next = Array(10).fill(0)
    for (let i = 0; i < 10; i++) {
      if (dist[i] === 0) continue
      for (let j = 0; j < 10; j++) next[j] += dist[i] * P[i][j]
    }
    dist = next
    let expected = 0
    for (let k = 0; k < 10; k++) expected += k * dist[k]
    const [p10, p90] = percentiles(dist, [0.1, 0.9])
    let pPoor = 0
    for (let k = 0; k <= threshold; k++) pPoor += dist[k]
    rows.push({
      year: y,
      expected: Math.round(expected * 100) / 100,
      p10,
      p90,
      p_poor: Math.round(pPoor * 10000) / 10000,
      dist: dist.map((v) => Math.round(v * 10000) / 10000),
    })
  }
  return rows
}

/** Mirror of backend deterioration.next_inspection (first year P(NBI<=4)>=25%). */
export function nextInspection(current: number, threshold = 4, pCross = 0.25): number | null {
  let dist = Array(10).fill(0)
  dist[Math.min(9, Math.max(0, Math.round(current)))] = 1.0
  const P = transitionMatrix()
  for (let y = 1; y <= 100; y++) {
    const next = Array(10).fill(0)
    for (let i = 0; i < 10; i++) {
      if (dist[i] === 0) continue
      for (let j = 0; j < 10; j++) next[j] += dist[i] * P[i][j]
    }
    dist = next
    let pPoor = 0
    for (let k = 0; k <= threshold; k++) pPoor += dist[k]
    if (pPoor >= pCross) return y
  }
  return null
}

/** Compute a full offline DeteriorationState from the current live BHI —
 * mirrors backend bridge_deterioration() with rating="super". */
export function fixtureDeterioration(bhi: number): DeteriorationState {
  const current = conditionFromBhi(bhi)
  return {
    currentBhi: Math.round(bhi * 10) / 10,
    currentCondition: current,
    priorsLabel: PRIORS_LABEL_OFFLINE,
    note: NOTE_OFFLINE,
    nextInspectionYear: nextInspection(current),
    nextInspectionRule: NEXT_RULE,
    projection: project(current, 30),
    rating: 'super',
  }
}

/** Whether the current live BHI is meaningful enough to anchor the fixture
 * (the store's live.bhi default 82.0 is fine; guard NaN only). */
export function fixtureReady(bhi: number): boolean {
  return Number.isFinite(bhi)
}
