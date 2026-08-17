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
import type { ChannelProvenance, SiteTempState } from '../store'
import { warnOnce } from './warnOnce'
import { apiBase } from './config'

const POLL_MS = 5000

// The only data sources the twin knows how to label.  Anything else on the wire
// (e.g. a future backend value the twin hasn't been taught) degrades to the
// honest 'offline' label instead of being cast through and shown verbatim.
const DATA_SOURCES = ['z24-replay', 'synthetic', 'live-demo', 'offline'] as const
type DataSource = (typeof DATA_SOURCES)[number]

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

const SITE_TEMP_SOURCES = ['open-meteo', 'synthetic'] as const
type SiteTempSource = (typeof SITE_TEMP_SOURCES)[number]

/**
 * NEW-02: guarded parse of the backend's site-temperature block.  Source
 * strings the twin was never taught degrade to the honest 'synthetic'
 * (modeled) label instead of being shown verbatim — a foreign claim can never
 * paint a modeled value as measured.  Returns null when the block is absent.
 */
export function parseSiteTemp(raw: unknown): SiteTempState | null {
  if (!raw || typeof raw !== 'object') return null
  const b = raw as Record<string, unknown>
  const src = typeof b.source === 'string' ? b.source : ''
  const source: SiteTempSource = SITE_TEMP_SOURCES.includes(src as SiteTempSource)
    ? (src as SiteTempSource)
    : 'synthetic'
  const tempC = typeof b.temp_c === 'number' ? (b.temp_c as number) : undefined
  return {
    tempC,
    source,
    sourceLabel:
      typeof b.source_label === 'string' ? (b.source_label as string) : undefined,
    cached: b.cached === true,
    fetchedAt: typeof b.fetched_at === 'number' ? (b.fetched_at as number) : null,
    note: typeof b.note === 'string' ? (b.note as string) : undefined,
  }
}

async function poll(): Promise<void> {
  try {
    const res = await fetch(`${apiBase()}/api/manifest`)
    if (!res.ok) return
    const m = (await res.json()) as Record<string, unknown>
    if (typeof m.data_source !== 'string') return
    const honesty = (m.honesty ?? {}) as Record<string, unknown>
    const live = (m.live_public_feed ?? {}) as Record<string, unknown>
    const rawSource = typeof m.data_source === 'string' ? m.data_source : ''
    const knownSource = (DATA_SOURCES as readonly string[]).includes(rawSource)
    const dataSource: DataSource = knownSource ? (rawSource as DataSource) : 'offline'
    const st = useStore.getState()
    st.setManifest({
      dataSource,
      dataSourceLabel: typeof m.data_source_label === 'string'
        ? (m.data_source_label as string)
        : knownSource
          ? rawSource
          : 'offline (unknown source from backend)',
      channels: mapChannels(m.channels),
      honestyNote: typeof honesty.note === 'string'
        ? (honesty.note as string)
        : 'Provenance manifest not available.',
      liveFeedActive: live.active === true,
      liveFeedBridge: typeof live.bridge === 'string' ? (live.bridge as string) : '',
      siteTemperature: parseSiteTemp(m.site_temperature),
    })
  } catch {
    // backend unreachable — honest offline default stays in effect
    warnOnce('manifest', 'GET /api/manifest failed — provenance panel shows offline default')
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
