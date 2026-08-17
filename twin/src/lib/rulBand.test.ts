import { describe, it, expect } from 'vitest'
import { yearsToPoor, formatBand, formatBandShort } from './rulBand'
import type { DeteriorationRow } from '../store'

/** Synthetic fan with NBI decaying monotonically, crossing NBI 4 on different
 * years per series — p10 (bad side) first, expected middle, p90 last. */
function fan(opts?: {
  p10Cross?: number
  expectedCross?: number
  p90Cross?: number
}): DeteriorationRow[] {
  const { p10Cross = 6, expectedCross = 12, p90Cross = 21 } = opts ?? {}
  const rows: DeteriorationRow[] = []
  for (let year = 1; year <= 30; year++) {
    const p10 = year >= p10Cross ? 4 : 6
    const expected = year >= expectedCross ? 3.9 : 6.2
    const p90 = year >= p90Cross ? 4 : 7
    rows.push({ year, expected, p10, p90, p_poor: 0, dist: [] })
  }
  return rows
}

describe('yearsToPoor — honest "years to NBI<=4" decision band', () => {
  it('crosses p10 first (bad side), expected middle, p90 last', () => {
    const band = yearsToPoor(fan(), 6)
    expect(band).toEqual({
      alreadyPoor: false,
      p10: 6,
      expected: 12,
      p90: 21,
      horizon: 30,
    })
  })

  it('already-poor condition is 0 years, not a projection', () => {
    expect(yearsToPoor(fan(), 4)).toEqual({
      alreadyPoor: true,
      p10: 0,
      expected: 0,
      p90: 0,
      horizon: 30,
    })
  })

  it('a series that never crosses within the horizon is null', () => {
    // p90 stays at 7 — never crosses NBI 4 in 30 years.
    const band = yearsToPoor(fan({ p90Cross: 99 }), 6)
    expect(band.p10).toBe(6)
    expect(band.expected).toBe(12)
    expect(band.p90).toBeNull()
  })

  it('empty projection + healthy condition -> null band (nothing to project)', () => {
    const band = yearsToPoor([], 8)
    expect(band.alreadyPoor).toBe(false)
    expect(band.p10).toBeNull()
    expect(band.expected).toBeNull()
    expect(band.p90).toBeNull()
  })
})

describe('formatBand / formatBandShort', () => {
  it('panel form carries the full range + expected', () => {
    expect(formatBand(yearsToPoor(fan(), 6))).toBe('6–21 yr (expected 12)')
  })
  it('null series renders as >horizon', () => {
    expect(formatBand(yearsToPoor(fan({ p90Cross: 99 }), 6))).toBe('6–>30 yr (expected 12)')
  })
  it('already-poor is explicit, not a fake number', () => {
    expect(formatBand(yearsToPoor(fan(), 4))).toContain('0 yr')
  })
  it('compact list form is short', () => {
    expect(formatBandShort(yearsToPoor(fan(), 6))).toBe('6–21 yr')
  })
})
