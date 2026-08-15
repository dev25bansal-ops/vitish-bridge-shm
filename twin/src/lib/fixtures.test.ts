import { describe, it, expect } from 'vitest'
import { mulberry32, generateFleet, FLEET_COUNT } from './fixtures'
import { stateFor } from '../store'

describe('mulberry32 — deterministic PRNG', () => {
  it('is deterministic for a fixed seed', () => {
    const a = mulberry32(20260813)
    const b = mulberry32(20260813)
    for (let i = 0; i < 100; i++) expect(a()).toBe(b())
  })

  it('returns values in [0, 1)', () => {
    const r = mulberry32(7)
    for (let i = 0; i < 1000; i++) {
      const v = r()
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThan(1)
    }
  })

  it('different seeds diverge on the first draw', () => {
    expect(mulberry32(1)()).not.toBe(mulberry32(2)())
  })
})

describe('generateFleet — deterministic offline fleet', () => {
  it('returns the hero + 49 regulators = 50 bridges', () => {
    expect(generateFleet()).toHaveLength(FLEET_COUNT)
  })

  it('hero z24 is first, GREEN at BHI 82, pinned at Nottwil (CH)', () => {
    const hero = generateFleet()[0]
    expect(hero.id).toBe('z24')
    expect(hero.name).toContain('Z24')
    expect(hero.bhi).toBe(82)
    expect(hero.state).toBe('GREEN')
    expect(hero.lat).toBeCloseTo(47.135, 3)
    expect(hero.lng).toBeCloseTo(8.165, 3)
  })

  it('is deterministic — two calls are identical', () => {
    expect(generateFleet()).toEqual(generateFleet())
  })

  it('every bridge state is consistent with its BHI via stateFor', () => {
    for (const b of generateFleet().slice(1)) {
      expect(b.state).toBe(stateFor(b.bhi))
    }
  })

  it('all lat/lng are finite and every id is unique', () => {
    const ids = new Set<string>()
    for (const b of generateFleet()) {
      expect(Number.isFinite(b.lat)).toBe(true)
      expect(Number.isFinite(b.lng)).toBe(true)
      expect(ids.has(b.id)).toBe(false)
      ids.add(b.id)
    }
  })
})
