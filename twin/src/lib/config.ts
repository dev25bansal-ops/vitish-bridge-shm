// Backend endpoint discovery.
//
// The twin used to hardcode http://127.0.0.1:8000 and ws://127.0.0.1:8765, but
// the backend walks to a free port when those are busy (backend/app/run_all.py
// probes 8001+ and 8766+).  On boot we ask /api/config (short timeout) for the
// actual bound ports and build URLs from them, falling back to the localhost
// defaults when the backend isn't up yet.  VITE_API_BASE / VITE_WS_URL override
// everything (see twin/.env.example) for a non-local deployment.
import { useStore } from '../store'
import { warnOnce } from './warnOnce'

const DEFAULT_API = 'http://127.0.0.1:8000'
const DEFAULT_WS = 'ws://127.0.0.1:8765'

interface Discovered {
  apiBase: string
  wsUrl: string
}

let cfg: Discovered | null = null
let tried = false

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

/** One-shot discovery of the backend's actual bound ports. Safe to await on
 *  boot; never throws (the default URLs stay in effect until it succeeds). */
export async function discoverConfig(timeoutMs = 2500): Promise<void> {
  if (tried) return
  tried = true
  try {
    const base = envApi() ?? DEFAULT_API
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), timeoutMs)
    let res: Response
    try {
      res = await fetch(`${base}/api/config`, { signal: ctrl.signal })
    } finally {
      clearTimeout(timer)
    }
    if (!res.ok) return
    const j = (await res.json()) as Record<string, unknown>
    const apiPort = typeof j.api_port === 'number' ? (j.api_port as number) : 8000
    const wsPort = typeof j.ws_port === 'number' ? (j.ws_port as number) : 8765
    cfg = {
      apiBase: envApi() ?? `http://127.0.0.1:${apiPort}`,
      wsUrl: envWs() ?? `ws://127.0.0.1:${wsPort}`,
    }
  } catch {
    // backend not up yet — ws.ts keeps retrying live every few seconds
    warnOnce('config', 'GET /api/config failed on boot — using default 127.0.0.1 ports (backend may start later)')
  }
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
