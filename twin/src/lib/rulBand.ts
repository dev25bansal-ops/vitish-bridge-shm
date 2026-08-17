// S1 "years to NBI<=4" decision band — mirror of the backend's
// deterioration.years_to_poor().  Computed from the projection fan the API
// already serves (and the offline fixture mirrors), so the live payload and the
// offline replay paint the same band.
//
// The p10 series is the low-NBI (bad-side) percentile and crosses NBI 4 first;
// p90 is the good-side percentile and crosses last; expected sits between.  A
// null year means "never within the horizon under that series".  Honest
// framing: a band of years under an empirical LTBP fleet prior, never a
// certified remaining life.
import type { DeteriorationRow } from '../store'

export interface YearsToPoorBand {
  alreadyPoor: boolean
  p10: number | null
  expected: number | null
  p90: number | null
  horizon: number
}

export function yearsToPoor(
  projection: DeteriorationRow[],
  currentCondition: number,
  horizon = 30,
  threshold = 4,
): YearsToPoorBand {
  if (currentCondition <= threshold) {
    return { alreadyPoor: true, p10: 0, expected: 0, p90: 0, horizon }
  }
  const first = (key: 'p10' | 'expected' | 'p90'): number | null => {
    for (const r of projection) {
      if (r[key] <= threshold) return r.year
    }
    return null
  }
  return {
    alreadyPoor: false,
    p10: first('p10'),
    expected: first('expected'),
    p90: first('p90'),
    horizon,
  }
}

function fmt(n: number | null, horizon: number): string {
  return n === null ? `>${horizon}` : `${n}`
}

/** "8–16 yr (expected 12)" — panel form (already-poor -> "0 yr …"). */
export function formatBand(b: YearsToPoorBand): string {
  if (b.alreadyPoor) return '0 yr (already at/below NBI 4)'
  return `${fmt(b.p10, b.horizon)}–${fmt(b.p90, b.horizon)} yr (expected ${fmt(b.expected, b.horizon)})`
}

/** "8–16 yr" — compact list form (already-poor -> "0 yr"). */
export function formatBandShort(b: YearsToPoorBand): string {
  if (b.alreadyPoor) return '0 yr'
  return `${fmt(b.p10, b.horizon)}–${fmt(b.p90, b.horizon)} yr`
}
