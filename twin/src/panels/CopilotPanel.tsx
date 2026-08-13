import { memo, useMemo } from 'react'
import { useStore } from '../store'
import type { Alert, LiveState, Scenario } from '../store'

/**
 * Mock copilot — plain-language maintenance recommendations keyed on alert
 * source. Honesty: this is a rule-based template engine, NOT an LLM, and the
 * UI says so.
 */
function copilotReply(a: Alert | undefined, live: LiveState, scenario: Scenario): string {
  if (!a) {
    return scenario === 'rupture'
      ? 'Damage scenario flagged by the storyboard. Waiting for corroborating vib/load evidence before recommending intervention.'
      : 'System nominal. No intervention required. Continue scheduled inspection cadence (90 days).'
  }
  const ev = `BHI ${live.bhi.toFixed(1)} (±${live.u.toFixed(1)}) · cv ${live.cv.toFixed(2)} · vib ${live.vib.toFixed(2)} · load ${live.load.toFixed(2)}`
  switch (a.source) {
    case 'fusion':
      return `Multi-modal fusion flags a ${a.severity} anomaly. Recommended: ${a.recommendation ?? 'impose load restriction and verify with strain gauges.'} Evidence: ${ev}.`
    case 'vib':
      return `Vibration channel exceeded threshold. Recommended: ${a.recommendation ?? 'raise sampling cadence and review modal frequencies.'} Evidence: ${ev}.`
    case 'cv':
      return `Visual branch: ${a.text.replace(/\.$/, '').toLowerCase()}. Recommended: ${a.recommendation ?? 'dispatch drone inspection within 48 h.'} Evidence: ${ev}.`
    case 'load':
      return `Loading signature abnormal. Recommended: ${a.recommendation ?? 'restrict traffic class and re-verify weigh-in-motion.'} Evidence: ${ev}.`
    default:
      return a.recommendation ?? 'Review anomaly and schedule verification.'
  }
}

export const CopilotPanel = memo(function CopilotPanel() {
  const alerts = useStore((s) => s.alerts)
  const live = useStore((s) => s.live)
  const scenario = useStore((s) => s.scenario)
  const latest = alerts[0]

  const reply = useMemo(() => copilotReply(latest, live, scenario), [latest, live, scenario])

  return (
    <section className="panel copilot">
      <header className="panel-title">
        Copilot <span className="panel-sub">rule-based · not an LLM</span>
      </header>
      <div className="copilot-bubble">{reply}</div>
      <div className="copilot-footer">
        Generated locally from canned templates keyed on alert source · review before action
      </div>
    </section>
  )
})
