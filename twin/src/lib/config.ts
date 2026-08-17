// Backend endpoint discovery.
//
// The twin used to hardcode http://127.0.0.1:8000 and ws://127.0.0.1:8765, but
// the backend walks to a free port when those are busy (backend/app/run_all.py
// probes 8001+ and 8766+).  On boot we ask /api/config (short timeout) for the
// actual bound ports and build URLs from them, falling back to the localhost
// defaults when the backend isn't up yet.  VITE_API_BASE / VITE_WS_URL override
// everything (see twin/.env.example) for a non-local deployment.
//
// BUG-04: discovery used to latch after ONE attempt (`tried = true` set before
// the fetch), so a backend that started LATE — or that walked to a fallback
// port because 8000 was busy at ITS boot — was never rediscovered: the twin
// stayed on the stale default URL forever.  Now discoverConfig() re-runs every
// call (ws.ts re-discovers before each connect attempt), latches the result
// ONLY on success, and walks the same API-port range the backend walks.
import { useStore } from '../store'
import { warnOnce } from './warnOnce'

const DEFAULT_API = 'http://127.0.0.1:8000'
const DEFAULT_WS = 'ws://127.0.0.1:8765'

// Mirrors backend/app/run_all.py `_find_free_port(attempts=20)`: the API binds
// the first free port in [8000, 8000+20), the WS bridge reports its actual port
// in the /api/config response.
const API_WALK_PORTS = 20
const PROBE_TIMEOUT_MS = 400
const ENV_PROBE_TIMEOUT_MS = 1500

interface Discovered {
  apiBase: string
  wsUrl: string
}

let cfg: Discovered | null = null // latched ONLY on a successful discovery

function envApi(): string | undefined {
  const v = import.meta.env.VITE_API_BASE
  return typeof v === 'string' && v.length > 0 ? v : undefined
}

function envWs(): string | undefined {
  const v = import.meta.env.VITE_WS_URL
  return typeof v === 'string' && v.length > 0 ? v : undefined
}

export function apiBase(): string {
  return cfg?.apiBase ?? envApi() ?? DEFAULT_API
}

export function wsUrl(): string {
  return cfg?.wsUrl ?? envWs() ?? DEFAULT_WS
}

/** Test hook: forget a previously discovered backend so a config.test can re-run
 *  the walk from a clean slate.  Never used by app code. */
export function resetDiscovery(): void {
  cfg = null
}

async function probe(base: string, timeoutMs: number): Promise<Discovered | null> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(`${base}/api/config`, { signal: ctrl.signal })
    if (!res.ok) return null
    const j = (await res.json()) as Record<string, unknown>
    const apiPort = typeof j.api_port === 'number' ? (j.api_port as number) : 8000
    const wsPort = typeof j.ws_port === 'number' ? (j.ws_port as number) : 8765
    // an env-pinned URL keeps its own base; otherwise the walked port wins.
    return envApi()
      ? { apiBase: envApi() as string, wsUrl: envWs() ?? DEFAULT_WS }
      : {
          apiBase: `http://127.0.0.1:${apiPort}`,
          wsUrl: `ws://127.0.0.1:${wsPort}`,
        }
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

/** Discover the backend's actual bound ports. Never throws; returns true when a
 *  live /api/config answered (and latches the result).  Walking the port range
 *  is cheap on localhost — a closed port refuses in milliseconds — so repeated
 *  calls (ws.ts re-discovers every connect attempt) do not stall the twin. */
export async function discoverConfig(timeoutMs = 2500): Promise<boolean> {
  // 1. Env pin (VITE_API_BASE) wins unconditionally — probe exactly that.
  const pin = envApi()
  if (pin) {
    const hit = await probe(pin, ENV_PROBE_TIMEOUT_MS)
    if (hit) cfg = hit
    return hit !== null
  }
  // 2. Cached backend still alive?  Single fast probe — restart at a new walked
  //    port is rare, and a failed probe just falls through to the walk below.
  if (cfg) {
    const hit = await probe(cfg.apiBase, PROBE_TIMEOUT_MS)
    if (hit) {
      cfg = hit // refresh ws_port in case the WS bridge moved
      return true
    }
  }
  // 3. Walk the API port range the backend walks, first responder wins.
  const startPort = 8000
  const deadline = Date.now() + timeoutMs
  for (let port = startPort; port < startPort + API_WALK_PORTS; port++) {
    if (Date.now() > deadline) break
    const hit = await probe(`http://127.0.0.1:${port}`, PROBE_TIMEOUT_MS)
    if (hit) {
      cfg = hit
      return true
    }
  }
  return false
}

/** Populate the bridge fleet from GET /api/bridges once the live path is up.
 *  Without this a backend-first session (WS up, no replay fixtures) would show
 *  an empty map and a '—' header.  No-op on failure (fixtures stay in effect). */
export async function fetchBridges(): Promise<void> {
  try {
    const res = await fetch(`${apiBase()}/api/bridges`)
    if (!res.ok) return
    const j = (await res.json()) as Record<string, unknown>
    const raw = Array.isArray(j.bridges) ? j.bridges : []
    const bridges = raw
      .filter(
        (b) =>
          b && typeof b === 'object' &&
          typeof (b as Record<string, unknown>).id === 'string',
      )
      .map((b) => {
        const x = b as Record<string, unknown>
        const lat = Number(x.lat ?? 0)
        const lon = Number(x.lon ?? x.lng ?? 0)
        return {
          id: x.id as string,
          name: String(x.name ?? ''),
          lat,
          lng: lon,
          bhi: Number(x.bhi ?? 0),
          state: (x.state as 'GREEN' | 'AMBER' | 'RED') ?? 'GREEN',
        }
      })
      .filter((b) => b.lat !== 0 || b.lng !== 0)
    if (bridges.length > 0) {
      useStore.getState().setBridges(bridges)
    }
  } catch {
    // backend unreachable — replay fixtures stay in effect
    warnOnce('bridges', 'GET /api/bridges failed — replay fixtures stay in effect')
  }
}