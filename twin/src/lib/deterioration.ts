// D2-11 Markov + Bayesian-updating poller — pulls the LTBP Markov projection
// (GET /api/bridge/z24/deterioration) and merges it into the store.  The curve
// is Bayesian in the sense that it re-anchors on every poll: the live BHI
// (which the crack state moves) re-maps to a current NBI condition, and the
// projection fans out from there.  Honest offline default when unreachable.
import { useStore } from '../store'
import type { DeteriorationRow } from '../store'

const DET_URL = 'http://127.0.0.1:8000/api/bridge/z24/deterioration?years=30&rating=super'
const POLL_MS = 5000

let timer: ReturnType<typeof setInterval> | null = null

function mapRows(raw: unknown): DeteriorationRow[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((r) => r && typeof r === 'object' && typeof r.year === 'number')
    .map((r) => {
      const x = r as Record<string, unknown>
      return {
        year: x.year as number,
        expected: Number(x.expected ?? 0),
        p10: Number(x.p10 ?? 0),
        p90: Number(x.p90 ?? 0),
        p_poor: Number(x.p_poor ?? 0),
        dist: Array.isArray(x.dist) ? (x.dist as number[]) : [],
      }
    })
}

async function poll(): Promise<void> {
  try {
    const res = await fetch(DET_URL)
    if (!res.ok) return
    const d = (await res.json()) as Record<string, unknown>
    if (!Array.isArray(d.projection)) return
    useStore.getState().setDeterioration({
      currentBhi: Number(d.current_bhi ?? 0),
      currentCondition: Number(d.current_condition ?? 0),
      priorsLabel: typeof d.priors_label === 'string' ? (d.priors_label as string) : '',
      note: typeof d.note === 'string' ? (d.note as string) : '',
      nextInspectionYear:
        typeof d.next_inspection_year === 'number' ? (d.next_inspection_year as number) : null,
      nextInspectionRule:
        typeof d.next_inspection_rule === 'string' ? (d.next_inspection_rule as string) : '',
      projection: mapRows(d.projection),
      rating: typeof d.rating === 'string' ? (d.rating as string) : 'super',
    })
  } catch {
    // backend unreachable — honest offline default stays in effect
  }
}

export function startDeteriorationPolling(): void {
  if (timer !== null) return
  poll()
  timer = setInterval(poll, POLL_MS)
}

export function stopDeteriorationPolling(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}
