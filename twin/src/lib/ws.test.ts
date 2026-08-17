import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll, vi } from 'vitest'
import { useStore, stateFor } from '../store'
import { connect, ingest } from './ws'

// --- harness ----------------------------------------------------------------
// ws.ts (via fixtures.ts) touches `window.setInterval` and `new WebSocket`.
// Node has neither by default, so point `window` at `globalThis` (timers exist
// there) and stub `WebSocket` with a controllable fake.  `fetchBridges()` on
// open must not hit the network, so `fetch` rejects instantly; `warnOnce`
// breadcrumbs are silenced.
class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  readyState = 0 // CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  close = vi.fn(() => {
    this.readyState = 3
  })

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  static open(i: number): void {
    const s = MockWebSocket.instances[i]
    s.readyState = 1
    s.onopen?.()
  }

  static err(i: number): void {
    MockWebSocket.instances[i].onerror?.()
  }

  static close(i: number): void {
    const s = MockWebSocket.instances[i]
    s.readyState = 3
    s.onclose?.()
  }

  static msg(i: number, data: string): void {
    MockWebSocket.instances[i].onmessage?.({ data })
  }
}

const initialLive = useStore.getState().live

beforeAll(() => {
  ;(globalThis as unknown as { window: unknown }).window = globalThis
  vi.stubGlobal('WebSocket', MockWebSocket)
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('no backend in unit tests'))))
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

beforeEach(() => {
  MockWebSocket.instances.length = 0
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

afterEach(() => {
  vi.useRealTimers()
})

afterAll(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// --- ingest guards ----------------------------------------------------------
describe('ingest — contract payload guards', () => {
  it('ignores null / non-object payloads', () => {
    const before = useStore.getState().live
    ingest(null)
    ingest(undefined)
    ingest('hello')
    ingest(42)
    expect(useStore.getState().live).toEqual(before)
  })

  it('applies the scenario cmd only for known scenarios', () => {
    ingest({ cmd: 'scenario', scenario: 'rupture' })
    expect(useStore.getState().scenario).toBe('rupture')
    useStore.getState().setScenario('healthy')
    ingest({ cmd: 'scenario', scenario: 'collapse-everything' })
    expect(useStore.getState().scenario).toBe('healthy')
  })

  it('accel: sets spectrum, rms, flag and node last-seen', () => {
    ingest({ bridge: 'z24', node: 7, samples: [1, -1, 1, -1, 1, -1], rms: 0.42, flag: 1 })
    const s = useStore.getState()
    expect(s.live.rms).toBe(0.42)
    expect(s.live.flag).toBe(1)
    expect(s.spectrum).toHaveLength(256)
    expect(s.nodeSeen[7]).toBeDefined()
  })

  it('accel without rms computes it from the samples', () => {
    ingest({ node: 6, samples: [3, 3, 3, 3] })
    expect(useStore.getState().live.rms).toBe(3)
  })

  it('bhi: sets bhi/u/cv/vib/load/state and the vib_evidence split', () => {
    ingest({
      bridge: 'z24',
      ts: 1,
      bhi: 55.5,
      u: 2.5,
      cv: 0.2,
      vib: 0.3,
      load: 0.4,
      state: 'AMBER',
      vib_evidence: { floor: 0.3, trained_push: 0.05, score: 0.3 },
    })
    const s = useStore.getState()
    expect(s.live.bhi).toBe(55.5)
    expect(s.live.u).toBe(2.5)
    expect(s.live.cv).toBe(0.2)
    expect(s.live.vib).toBe(0.3)
    expect(s.live.load).toBe(0.4)
    expect(s.live.state).toBe('AMBER')
    expect(s.live.vibEvidence).toEqual({ floor: 0.3, trained_push: 0.05, score: 0.3 })
  })

  it('bhi without state derives it from the value', () => {
    ingest({ bhi: 55.5 })
    expect(useStore.getState().live.state).toBe(stateFor(55.5))
  })

  it('alert: pushes with severity/source coercion to the known sets', () => {
    ingest({ severity: 'nuclear', source: 'nonsense', text: 'x' })
    const a = useStore.getState().alerts[0]
    expect(a.severity).toBe('info')
    expect(a.source).toBe('fusion')
    expect(a.text).toBe('x')
  })

  it('frame with detections raises a cv alert; an empty frame is silent', () => {
    ingest({ cam: 'cam1', image_b64: 'AAAA', detections: [{ cls: 'crack', conf: 0.9 }] })
    expect(useStore.getState().alerts).toHaveLength(1)
    expect(useStore.getState().alerts[0].source).toBe('cv')
    ingest({ cam: 'cam1', image_b64: 'BBBB', detections: [] })
    expect(useStore.getState().alerts).toHaveLength(1)
  })
})

// --- state machine ----------------------------------------------------------
describe('connect — WS state machine (LIVE → REPLAY → retry)', () => {
  it('opens to LIVE, unwraps the envelope, drops to REPLAY, and retries forever', async () => {
    vi.useFakeTimers()

    connect()
    // BUG-04: attempt() awaits port re-discovery before dialing (capped), so the
    // socket appears on a microtask flush rather than synchronously.
    await vi.advanceTimersByTimeAsync(0)
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toBe('ws://127.0.0.1:8765')

    // open → LIVE
    MockWebSocket.open(0)
    expect(useStore.getState().wsStatus).toBe('live')

    // envelope-wrapped BHI message → unwrapped and ingested
    MockWebSocket.msg(0, JSON.stringify({ topic: 'bridge/z24/bhi', payload: { bhi: 60, state: 'AMBER' } }))
    expect(useStore.getState().live.bhi).toBe(60)
    expect(useStore.getState().live.state).toBe('AMBER')

    // malformed frame is swallowed, not thrown
    MockWebSocket.msg(0, '{broken json')
    expect(useStore.getState().live.bhi).toBe(60)

    // dropped connection → honest REPLAY + retry armed
    MockWebSocket.close(0)
    expect(useStore.getState().wsStatus).toBe('replay')

    // 5 s later the retry dials a fresh socket (discovery → microtask)
    vi.advanceTimersByTime(5000)
    await vi.advanceTimersByTimeAsync(0)
    expect(MockWebSocket.instances).toHaveLength(2)
    MockWebSocket.open(1)
    expect(useStore.getState().wsStatus).toBe('live')

    // drop again, let the retried socket hang: 3 s timeout → REPLAY again
    MockWebSocket.close(1)
    expect(useStore.getState().wsStatus).toBe('replay')
    vi.advanceTimersByTime(5000)
    await vi.advanceTimersByTimeAsync(0)
    expect(MockWebSocket.instances).toHaveLength(3)
    vi.advanceTimersByTime(3000) // fallback timeout on the unopened socket
    expect(useStore.getState().wsStatus).toBe('replay')
    vi.advanceTimersByTime(5000) // and it keeps retrying
    await vi.advanceTimersByTimeAsync(0)
    expect(MockWebSocket.instances).toHaveLength(4)
  })
})
