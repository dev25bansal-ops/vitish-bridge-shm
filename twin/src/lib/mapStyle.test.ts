import { describe, it, expect } from 'vitest'
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec'
import type { StyleSpecification } from '@maplibre/maplibre-gl-style-spec'
import { matchStateColor } from './mapStyle'
import { STATE_COLORS, NEUTRAL } from './theme'

/** The two paint properties BridgeMap drives with the shared match expression. */
function styleWith(expr: ReturnType<typeof matchStateColor>): StyleSpecification {
  return {
    version: 8,
    sources: {
      bridges: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
    },
    layers: [
      { id: 'bridges-fill', type: 'fill', source: 'bridges', paint: { 'fill-color': expr } },
      { id: 'bridges-ring', type: 'circle', source: 'bridges', paint: { 'circle-color': expr } },
    ],
  }
}

describe('matchStateColor — MapLibre style-spec validity (would have caught the BridgeMap bug)', () => {
  it('validates clean against the REAL style-spec validator', () => {
    const errors = validateStyleMin(styleWith(matchStateColor()))
    expect(errors).toEqual([])
  })

  it('is a 3-branch match on state with the shared palette + neutral fallback', () => {
    const expr = matchStateColor()
    expect(expr[0]).toBe('match')
    expect(expr[1]).toEqual(['get', 'state'])
    expect(expr[2]).toBe('RED')
    expect(expr[3]).toBe(STATE_COLORS.RED)
    expect(expr[4]).toBe('AMBER')
    expect(expr[5]).toBe(STATE_COLORS.AMBER)
    expect(expr[6]).toBe('GREEN')
    expect(expr[7]).toBe(STATE_COLORS.GREEN)
    expect(expr[8]).toBe(NEUTRAL)
  })

  it('rejects the pre-fix failure mode (a state name where a color belongs)', () => {
    // Line-83 bug class: the old expression put a state *name* in a color slot.
    // The validator must flag it — this test guards the real failure mode.
    const broken = [
      'match',
      ['get', 'state'],
      'RED', 'AMBER', // ← 'AMBER' is a state name, not a color
      'GREEN', '#16a34a',
      '#7c8ea0', // fallback
    ]
    const errors = validateStyleMin(styleWith(broken as ReturnType<typeof matchStateColor>))
    expect(errors.length).toBeGreaterThan(0)
    expect(errors[0].message).toContain('Could not parse color')
  })
})
