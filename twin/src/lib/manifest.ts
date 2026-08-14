// D1-5/D1-6 data-realism manifest poller — pulls GET /api/manifest from the
// backend and merges it into the store.  This is the honest "what am I actually
// looking at?" contract: every channel is labeled real Z24 replay | modeled
// synthetic | third-party live-demo, and the digital-shadow / one-way-data note
// comes straight from the backend manifest, never from the frontend.
//
// Falls back to the honest OFFLINE default silently: if the backend is down the
// store keeps "replay fixtures (backend unreachable)" and the provenance panel
// shows the offline state instead of inventing a data source.
import { useStore } from '../store'
import type { ChannelProvenance } from '../store'

const MANIFEST_URL = 'http://127.0.0.1:8000/api/manifest'
const POLL_MS = 5000

let timer: ReturnType<typeof setInterval> | null = null

/** Guarded mapping — never trust the wire format, never crash on a bad field. */
function mapChannels(raw: unknown): ChannelProvenance[] {
  if (!raw || typeof raw !== 'object') return []
  const byNode = raw as Record<string, Record<string, unknown>>
  return Object.entries(byNode)
    .filter(([node]) => /^\d+$/.test(node))
    .map(([node, e]) => ({
      node: Number(node),
      source: typeof e?.source === 'string' ? e.source : 'synthetic',
      real: e?.real === true,
      sensor: typeof e?.sensor === 'string' ? e.sensor : `node ${node}`,
    }))
    .sort((a, b) => a.node - b.node)
}

async function poll(): Promise<void> {
  try {
    const res = await fetch(MANIFEST_URL)
    if (!res.ok) return
    const m = (await res.json()) as Record<string, unknown>
    if (typeof m.data_source !== 'string') return
    const honesty = (m.honesty ?? {}) as Record<string, unknown>
    const live = (m.live_public_feed ?? {}) as Record<string, unknown>
    const st = useStore.getState()
    st.setManifest({
      dataSource: (m.data_source as 'z24-replay' | 'synthetic' | 'live-demo' | 'offline') ?? 'offline',
      dataSourceLabel: typeof m.data_source_label === 'string'
        ? (m.data_source_label as string)
        : String(m.data_source),
      channels: mapChannels(m.channels),
      honestyNote: typeof honesty.note === 'string'
        ? (honesty.note as string)
        : 'Provenance manifest not available.',
      liveFeedActive: live.active === true,
      liveFeedBridge: typeof live.bridge === 'string' ? (live.bridge as string) : '',
    })
  } catch {
    // backend unreachable — honest offline default stays in effect
  }
}

export function startManifestPolling(): void {
  if (timer !== null) return
  poll()
  timer = setInterval(poll, POLL_MS)
}

export function stopManifestPolling(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}
