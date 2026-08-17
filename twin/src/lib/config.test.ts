// BUG-04 regression: backend discovery must NOT latch after one failed attempt.
// The reviewer found the twin never rediscovered a backend that booted late or
// walked to a fallback port, because config.ts set a `tried` latch BEFORE the
// fetch.  These tests pin: (1) defaults on a totally-absent backend, (2) the
// API-port walk [8000, 8000+20) finding a walked backend, (3) a SECOND discovery
// call (the ws.ts reconnect path) finding a backend that appeared late.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { apiBase, wsUrl, discoverConfig, resetDiscovery } from './config'

function ok(apiPort: number, wsPort: number): Response {
  return new Response(JSON.stringify({ api_port: apiPort, ws_port: wsPort }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

/** Mock fetch: rejects for `rejectPorts`, serves /api/config on the rest. */
function stubFetch(rejectPorts: Set<number>): void {
  const fetcher = vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url)
    const m = u.match(/127\.0\.0\.1:(\d+)\/api\/config$/)
    const port = m ? Number(m[1]) : NaN
    if (Number.isNaN(port) || rejectPorts.has(port)) {
      throw new TypeError('fetch failed: connection refused')
    }
    return ok(port, port === 8000 ? 8765 : port + 4) // ws bridge walks too
  })
  vi.stubGlobal('fetch', fetcher)
}

beforeEach(() => resetDiscovery())
afterEach(() => vi.unstubAllGlobals())

describe('discoverConfig — BUG-04 non-latching port discovery', () => {
  it('falls back to localhost defaults when no backend answers (returns false)', async () => {
    stubFetch(new Set(Array.from({ length: 20 + 1 }, (_, i) => 8000 + i)))
    await expect(discoverConfig()).resolves.toBe(false)
    expect(apiBase()).toBe('http://127.0.0.1:8000')
    expect(wsUrl()).toBe('ws://127.0.0.1:8765')
  })

  it('walks the API port range and uses the reported ws port', async () => {
    const dead = new Set<number>()
    for (let p = 8000; p <= 8002; p++) dead.add(p)
    stubFetch(dead) // backend walked to 8003; reports its ws bridge on 8007
    await expect(discoverConfig()).resolves.toBe(true)
    expect(apiBase()).toBe('http://127.0.0.1:8003')
    expect(wsUrl()).toBe('ws://127.0.0.1:8007')
  })

  it('re-discovery finds a backend that started LATE (the actual bug)', async () => {
    // first call: everything dead -> defaults, NO latch
    stubFetch(new Set(Array.from({ length: 21 }, (_, i) => 8000 + i)))
    await expect(discoverConfig()).resolves.toBe(false)
    expect(apiBase()).toBe('http://127.0.0.1:8000')
    // backend now boots late, 8000 still busy -> it walks to 8004
    const dead = new Set<number>()
    for (let p = 8000; p <= 8003; p++) dead.add(p)
    stubFetch(dead)
    await expect(discoverConfig()).resolves.toBe(true)
    expect(apiBase()).toBe('http://127.0.0.1:8004')
  })
})