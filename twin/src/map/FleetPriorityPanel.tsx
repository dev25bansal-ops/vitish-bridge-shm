// S1 fleet-priority card — the "which bridge first, and when" decision surface
// overlaid on the fleet map.  Ranks the fleet by next-inspection year (most
// urgent first) and shows each bridge's "years to NBI<=4" band.
//
// Source priority:
//   1. LIVE  — GET /api/fleet/priority (backend Markov projection + honest
//              labels, priors from the real LTBP summary).
//   2. OFFLINE — mirror computed from the store's bridges with the SAME
//              deteriorationFixture Markov mirror the DeteriorationPanel uses,
//              so the card is never empty while the backend is down.
//
// Honest framing (always rendered): the 49 regulator healths are
// seeded/illustrative; every number is a Markov projection under an empirical
// LTBP fleet prior, small n — never a certified RUL.
import { memo, useEffect, useState } from 'react'
import { useStore } from '../store'
import { apiBase } from '../lib/config'
import { conditionFromBhi, nextInspection, project } from '../lib/deteriorationFixture'
import { yearsToPoor, formatBandShort } from '../lib/rulBand'
import type { YearsToPoorBand } from '../lib/rulBand'
import { stateHex } from '../lib/theme'
import { warnOnce } from '../lib/warnOnce'

const POLL_MS = 5000
const LIMIT = 8

interface PrioRow {
  rank: number
  id: string
  name: string
  state: string
  bhi: number
  nextInspectionYear: number | null
  band: YearsToPoorBand
  live: boolean
  hero: boolean
}

/** Offline mirror of GET /api/fleet/priority — same rank (next-inspection
 * asc, then band-expected), computed from the store's bridges. */
function offlineRows(): PrioRow[] {
  const bridges = useStore.getState().bridges
  const rows = bridges.map((b) => {
    const current = conditionFromBhi(b.bhi)
    return {
      rank: 0,
      id: b.id,
      name: b.name,
      state: b.state,
      bhi: b.bhi,
      nextInspectionYear: nextInspection(current),
      band: yearsToPoor(project(current, 30), current),
      live: b.id === 'z24',
      hero: b.id === 'z24',
    }
  })
  rows.sort((a, b) => {
    const ai = a.nextInspectionYear ?? 1e9
    const bi = b.nextInspectionYear ?? 1e9
    if (ai !== bi) return ai - bi
    return (a.band.expected ?? 1e9) - (b.band.expected ?? 1e9)
  })
  return rows.slice(0, LIMIT).map((r, i) => ({ ...r, rank: i + 1 }))
}

function parseLive(j: Record<string, unknown>): PrioRow[] {
  const raw = Array.isArray(j.rows) ? j.rows : []
  return raw
    .filter(
      (r) =>
        r && typeof r === 'object' &&
        typeof (r as Record<string, unknown>).id === 'string',
    )
    .map((r) => {
      const x = r as Record<string, unknown>
      const y = (x.years_to_poor ?? {}) as Record<string, unknown>
      const band: YearsToPoorBand = {
        alreadyPoor: Boolean(y.alreadyPoor),
        p10: typeof y.p10 === 'number' ? (y.p10 as number) : null,
        expected: typeof y.expected === 'number' ? (y.expected as number) : null,
        p90: typeof y.p90 === 'number' ? (y.p90 as number) : null,
        horizon: typeof y.horizon === 'number' ? (y.horizon as number) : 30,
      }
      return {
        rank: Number(x.rank ?? 0),
        id: x.id as string,
        name: String(x.name ?? ''),
        state: String(x.state ?? 'GREEN'),
        bhi: Number(x.bhi ?? 0),
        nextInspectionYear:
          typeof x.next_inspection_year === 'number'
            ? (x.next_inspection_year as number)
            : null,
        band,
        live: Boolean(x.live),
        hero: Boolean(x.hero),
      }
    })
}

export const FleetPriorityPanel = memo(function FleetPriorityPanel() {
  const [rows, setRows] = useState<PrioRow[]>(() => offlineRows())
  const [source, setSource] = useState<'live' | 'offline'>('offline')

  useEffect(() => {
    let alive = true
    const tick = async () => {
      let parsed: PrioRow[] = []
      try {
        const res = await fetch(`${apiBase()}/api/fleet/priority?limit=${LIMIT}`)
        if (res.ok) parsed = parseLive((await res.json()) as Record<string, unknown>)
      } catch {
        parsed = [] // fall through to the offline mirror
      }
      if (!alive) return
      if (parsed.length > 0) {
        setRows(parsed)
        setSource('live')
      } else {
        warnOnce('fleet-priority', 'GET /api/fleet/priority failed — offline mirror')
        const off = offlineRows()
        if (off.length > 0) {
          setRows(off)
          setSource('offline')
        }
      }
    }
    tick()
    const timer = setInterval(tick, POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  if (rows.length === 0) return null

  return (
    <div className="fleet-priority">
      <div className="fp-head">
        Inspection priority · top {rows.length}
        <span className={`fp-src ${source}`}>
          {source === 'live' ? 'Markov' : 'offline mirror'}
        </span>
      </div>
      <div className="fp-list">
        {rows.map((r) => (
          <div
            className="fp-row"
            key={r.id}
            title={`${r.name} · BHI ${r.bhi.toFixed(1)}${r.live ? ' · LIVE' : ''}`}
          >
            <span className="fp-rank">{r.rank}</span>
            <span
              className="fp-dot"
              style={{ background: stateHex(r.state as 'GREEN' | 'AMBER' | 'RED') }}
            />
            <span className="fp-name">{r.name}</span>
            <span className="fp-inspect">
              {r.nextInspectionYear !== null ? `yr ${r.nextInspectionYear}` : '—'}
            </span>
            <span className="fp-band">{formatBandShort(r.band)}</span>
          </div>
        ))}
      </div>
      <div className="fp-honesty">
        Markov projection, LTBP fleet prior — not certified RUL · 49 regulators illustrative
      </div>
    </div>
  )
})
