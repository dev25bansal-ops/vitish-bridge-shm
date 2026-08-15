import { describe, it, expect, beforeEach } from 'vitest'
import {
  resetCollapse,
  tickCollapse,
  deckYAt,
  wobble,
  modePhi1,
  modeFreq1,
  collapseState,
  BRIDGE,
  DAMAGE_SAT_PCT,
} from './collapse'
import { useStore, F1_REF_HZ } from '../store'

// collapse.ts drives a module-level mutable collapseState + the store's
// stiffness overlay; reset both so tests are independent.
beforeEach(() => {
  resetCollapse()
  useStore.setState({
    stiffness: { ...useStore.getState().stiffness, shapes: [], x: [], freqs: [F1_REF_HZ] },
  })
})

describe('collapse story arc — no flicker, no snapping', () => {
  it('starts healthy (sag 0, cascade 0)', () => {
    expect(collapseState.sag).toBe(0)
    expect(collapseState.cascade).toBe(0)
  })

  it('rupture is monotonic non-decreasing to full sag then full cascade (never snaps down)', () => {
    let prevSag = collapseState.sag
    let prevCascade = collapseState.cascade
    for (let i = 0; i < 1000; i++) {
      tickCollapse('rupture', 1 / 60)
      expect(collapseState.sag).toBeGreaterThanOrEqual(prevSag - 1e-9)
      expect(collapseState.cascade).toBeGreaterThanOrEqual(prevCascade - 1e-9)
      prevSag = collapseState.sag
      prevCascade = collapseState.cascade
    }
    expect(collapseState.sag).toBeGreaterThan(0.999)
    expect(collapseState.cascade).toBeGreaterThan(0.999)
  })

  it('deflection precedes flexing (cascade lags sag at the onset)', () => {
    for (let i = 0; i < 150; i++) tickCollapse('rupture', 1 / 60) // ~2.5 s in
    expect(collapseState.sag).toBeGreaterThan(0.01)
    expect(collapseState.cascade).toBeLessThan(0.01)
  })

  it('healthy recovery returns both to 0 (no residual droop)', () => {
    for (let i = 0; i < 1000; i++) tickCollapse('rupture', 1 / 60)
    for (let i = 0; i < 400; i++) tickCollapse('healthy', 1 / 60)
    expect(collapseState.sag).toBeLessThan(1e-3)
    expect(collapseState.cascade).toBeLessThan(1e-3)
  })
})

describe('deckYAt — exaggerated visual droop', () => {
  it('healthy deck sits at BRIDGE.deckY (6 m)', () => {
    expect(deckYAt(0)).toBeCloseTo(BRIDGE.deckY, 9)
    expect(deckYAt(14)).toBeCloseTo(BRIDGE.deckY, 9)
  })

  it('droops ~1.7 m at mid-span under full sag, ~0 at the piers', () => {
    for (let i = 0; i < 1000; i++) tickCollapse('rupture', 1 / 60)
    const mid = deckYAt(0)
    const pier = deckYAt(BRIDGE.pierX)
    expect(mid).toBeLessThan(BRIDGE.deckY - 1.6)
    expect(mid).toBeLessThan(pier)
    expect(pier).toBeGreaterThan(BRIDGE.deckY - 0.4)
  })

  it('is symmetric in x', () => {
    for (let i = 0; i < 1000; i++) tickCollapse('rupture', 1 / 60)
    expect(deckYAt(-5)).toBeCloseTo(deckYAt(5), 9)
  })
})

describe('wobble — exaggerated first-mode flexing, gated on cascade', () => {
  it('is zero when cascade is zero (healthy deck is still)', () => {
    expect(wobble(0, 1.234)).toBe(0)
    expect(wobble(-10, 0)).toBe(0)
  })

  it('is bounded by 0.7 · cascade · modePhi1(x)', () => {
    collapseState.cascade = 0.5
    for (const x of [0, 5, -7, 15]) {
      const bound = 0.7 * 0.5 * Math.abs(modePhi1(x))
      for (const t of [0, 0.05, 0.11, 0.5]) {
        expect(Math.abs(wobble(x, t))).toBeLessThanOrEqual(bound + 1e-9)
      }
    }
  })
})

describe('modePhi1 — main-span first mode', () => {
  it('fallback is zero at the interior piers, peak at mid-span', () => {
    expect(Math.abs(modePhi1(-BRIDGE.mainHalf))).toBeLessThan(1e-9)
    expect(Math.abs(modePhi1(BRIDGE.mainHalf))).toBeLessThan(1e-9)
    expect(modePhi1(0)).toBeCloseTo(1, 9)
  })

  it('interpolates the FEM snapshot when the backend overlay is present', () => {
    useStore.setState({
      stiffness: {
        ...useStore.getState().stiffness,
        x: [0, 29, 58],
        shapes: [[0, 1, 0]],
      },
    })
    expect(modePhi1(-BRIDGE.half)).toBeCloseTo(0, 6) // scene x=-29 → FEM x=0
    expect(modePhi1(0)).toBeCloseTo(1, 6) // scene x=0 → FEM x=29 (mid-span)
    expect(modePhi1(BRIDGE.half)).toBeCloseTo(0, 6) // scene x=+29 → FEM x=58
  })
})

describe('modeFreq1 — measured first vertical mode', () => {
  it('falls back to F1_REF_HZ when the overlay has no frequencies', () => {
    useStore.setState({ stiffness: { ...useStore.getState().stiffness, freqs: [] } })
    expect(modeFreq1()).toBe(F1_REF_HZ)
  })

  it('reads the first FEM frequency when present', () => {
    useStore.setState({ stiffness: { ...useStore.getState().stiffness, freqs: [2.5, 10.2] } })
    expect(modeFreq1()).toBe(2.5)
  })
})

describe('DAMAGE_SAT_PCT — shared saturation constant', () => {
  it('is 35 and shared by MorbiBridge.segColor + the SceneOverlay legend', () => {
    // Both consumers import THIS constant (grep-verified), so the scene tint and
    // the "35%+" legend label can never desync.
    expect(DAMAGE_SAT_PCT).toBe(35)
  })
})
