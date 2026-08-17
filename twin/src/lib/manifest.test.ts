import { describe, expect, it } from 'vitest'
import { parseSiteTemp } from './manifest'

// NEW-02: the honest site-temperature block must preserve the backend's source
// label and never let a foreign/unknown source paint a value as measured.
describe('parseSiteTemp', () => {
  it('parses a measured Open-Meteo block', () => {
    const s = parseSiteTemp({
      temp_c: 21.3,
      source: 'open-meteo',
      source_label: 'measured air temperature — Open-Meteo forecast (Koppigen A1)',
      cached: true,
      fetched_at: 1_700_000_000,
      note: 'display only',
    })
    expect(s).not.toBeNull()
    expect(s?.tempC).toBe(21.3)
    expect(s?.source).toBe('open-meteo')
    expect(s?.cached).toBe(true)
    expect(s?.sourceLabel).toContain('measured')
  })

  it('keeps the simulated fallback label on the synthetic path', () => {
    const s = parseSiteTemp({
      temp_c: 5.2,
      source: 'synthetic',
      source_label: 'simulated seasonal temperature (day-of-year model) — not a measured sensor',
    })
    expect(s?.source).toBe('synthetic')
    expect(s?.sourceLabel).toContain('not a measured sensor')
  })

  it('degrades an unknown source to synthetic (never measured)', () => {
    const s = parseSiteTemp({ temp_c: 12.0, source: 'government-api-v3' })
    expect(s?.source).toBe('synthetic')
  })

  it('returns null for a missing block', () => {
    expect(parseSiteTemp(undefined)).toBeNull()
    expect(parseSiteTemp(null)).toBeNull()
    expect(parseSiteTemp(42)).toBeNull()
  })

  it('survives a malformed block without crashing', () => {
    const s = parseSiteTemp({ temp_c: 'warm', source: 7 })
    expect(s?.source).toBe('synthetic')
    expect(s?.tempC).toBeUndefined()
  })
})