import { memo } from 'react'
import { useStore } from '../store'

/**
 * D2-8 simulated-clock chip — the authoritative monitoring time is a MODEL,
 * not wall-clock: the Z24 campaign ran 11 Nov 1998 → 20 Aug 1999 (~9 months),
 * and the twin plays it back at a time-lapse.  Every temporal claim on screen
 * is anchored to this simulated day-of-year, never to "now".
 *
 * Reads the backend sim_clock (backend/app/sim_clock.py) via the stiffness
 * overlay; renders nothing until the backend reports one.
 */
export const SimClockBadge = memo(function SimClockBadge() {
  const simClock = useStore((s) => s.stiffness.simClock)
  const simDay = useStore((s) => s.stiffness.simDay)
  const tempC = useStore((s) => s.stiffness.tempC)
  const f1Ref = useStore((s) => s.stiffness.f1Ref)

  if (!simClock) return null

  const day = simDay !== undefined ? Math.round(simDay) : null
  const temp = tempC !== undefined ? ` · ${tempC.toFixed(1)}°C sim` : ''

  return (
    <div className="sim-clock-badge" title="Simulated monitoring time (time-lapse playback) — never wall-clock">
      <span className="sim-clock-label">SIM</span>
      <span className="sim-clock-val">{day !== null ? `day ${day}/365` : simClock}</span>
      <span className="sim-clock-meta">×2 d/s · f1-ref {f1Ref.toFixed(2)} Hz{temp}</span>
    </div>
  )
})
