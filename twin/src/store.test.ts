import { describe, it, expect, beforeEach } from 'vitest'
import { computeBhi, stateFor, useStore, BHI_GREEN, BHI_AMBER, BHI_W } from './store'

// Backend-parity constants pinned from backend/app/contract.py `compute_bhi` —
// the SAME weighted penalty, clamp, and round-to-0.1 the Python reference
// returns for these inputs (verified against the repo before pinning).  A drift
// here means the twin's BHI diverges from the backend that drives the demo arc.
describe('computeBhi — backend contract parity (3-arg form)', () => {
  const cases: Array<[number, number, number, number]> = [
    [0.0, 0.0, 0.0, 100.0],
    [0.12, 0.14, 0.3, 82.8],
    [0.4, 0.35, 0.25, 65.5], // full-weight damage → AMBER
    [1.0, 1.0, 1.0, 0.0],
    [2.0, -1.0, 0.5, 47.5], // clamped to [0,1]
    [0.5, 0.0, 0.0, 80.0],
    [0.0, 0.5, 0.0, 82.5],
    [0.0, 0.0, 0.5, 87.5],
    [0.1234, 0.0, 0.0, 95.1], // round-to-0.1
  ]
  it.each(cases)('computeBhi(%s, %s, %s) === %s', (cv, vib, load, expected) => {
    expect(computeBhi(cv, vib, load)).toBe(expected)
  })

  it('uses BHI_W weights 0.40 / 0.35 / 0.25 (a single 1.0 component loses exactly its weight)', () => {
    expect(computeBhi(1, 0, 0)).toBe(100 * (1 - BHI_W.cv))
    expect(computeBhi(0, 1, 0)).toBe(100 * (1 - BHI_W.vib))
    expect(computeBhi(0, 0, 1)).toBe(100 * (1 - BHI_W.load))
  })

  it('age/traffic factors scale the result (backend parity: 72.0 / 68.0 / 61.2)', () => {
    expect(computeBhi(0.2, 0.2, 0.2, 0.9, 1.0)).toBe(72.0)
    expect(computeBhi(0.2, 0.2, 0.2, 1.0, 0.85)).toBe(68.0)
    expect(computeBhi(0.2, 0.2, 0.2, 0.9, 0.85)).toBe(61.2)
  })

  it('is monotone non-increasing in every component', () => {
    for (let i = 0; i <= 20; i++) {
      const x = i / 20
      const base = computeBhi(x, 0.1, 0.1)
      expect(computeBhi(x + 0.05, 0.1, 0.1)).toBeLessThanOrEqual(base)
      expect(computeBhi(0.1, x, 0.1)).toBeLessThanOrEqual(computeBhi(0.1, x - 0.001, 0.1))
      expect(computeBhi(0.1, 0.1, x)).toBeLessThanOrEqual(computeBhi(0.1, 0.1, x - 0.001))
    }
  })
})

describe('stateFor — BHI band boundaries', () => {
  it('GREEN >= 70, AMBER [50, 70), RED < 50', () => {
    expect(stateFor(100)).toBe('GREEN')
    expect(stateFor(BHI_GREEN)).toBe('GREEN')
    expect(stateFor(BHI_GREEN - 0.1)).toBe('AMBER')
    expect(stateFor(BHI_AMBER)).toBe('AMBER')
    expect(stateFor(BHI_AMBER - 0.1)).toBe('RED')
    expect(stateFor(0)).toBe('RED')
  })
})

describe('store slices', () => {
  const initialLive = useStore.getState().live

  beforeEach(() => {
    useStore.setState({
      live: { ...initialLive },
      bhiTrend: [],
      alerts: [],
      nodeSeen: {},
      scenario: 'healthy',
      wsStatus: 'connecting',
      bridges: [],
    })
  })

  it('setLive with bhi derives state and appends to the trend (capped at 120)', () => {
    const s = useStore.getState()
    for (let i = 0; i < 150; i++) s.setLive({ bhi: 50 })
    const st = useStore.getState()
    expect(st.live.state).toBe('AMBER') // 50 >= BHI_AMBER
    expect(st.bhiTrend).toHaveLength(120)
    expect(st.bhiTrend[0]).toBe(50)
    expect(st.bhiTrend[119]).toBe(50)
  })

  it('setLive without bhi does not touch the trend', () => {
    useStore.getState().setLive({ rms: 0.33 })
    expect(useStore.getState().bhiTrend).toHaveLength(0)
  })

  it('pushAlert prepends newest-first and caps at 40', () => {
    const s = useStore.getState()
    for (let i = 0; i < 50; i++) s.pushAlert({ severity: 'info', source: 'cv', text: `a${i}` })
    const alerts = useStore.getState().alerts
    expect(alerts).toHaveLength(40)
    expect(alerts[0].text).toBe('a49')
    expect(alerts[39].text).toBe('a10')
  })

  it('setNodeSeen is idempotent for a repeated timestamp (no churn)', () => {
    const s = useStore.getState()
    s.setNodeSeen(7, 1000)
    const seen = useStore.getState().nodeSeen
    s.setNodeSeen(7, 1000)
    expect(useStore.getState().nodeSeen).toBe(seen) // same object identity → no re-render
  })
})
