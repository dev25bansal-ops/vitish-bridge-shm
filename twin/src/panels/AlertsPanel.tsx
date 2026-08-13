import { memo } from 'react'
import { useStore } from '../store'

function fmtTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour12: false })
}

/** Alert stream, newest first; latest alert highlighted. */
export const AlertsPanel = memo(function AlertsPanel() {
  const alerts = useStore((s) => s.alerts)

  return (
    <section className="panel">
      <header className="panel-title">
        Alerts <span className="panel-sub">{alerts.length}</span>
      </header>
      <div className="alert-list">
        {alerts.length === 0 && <div className="alert-empty">No alerts yet</div>}
        {alerts.map((a, i) => (
          <div key={a.id} className={`alert severity-${a.severity}${i === 0 ? ' latest' : ''}`}>
            <div className="alert-row">
              <span className="alert-sev">{a.severity}</span>
              <span className="alert-time">{fmtTime(a.ts)}</span>
              <span className="alert-src">{a.source}</span>
            </div>
            <div className="alert-text">{a.text}</div>
            {i === 0 && a.recommendation && (
              <div className="alert-reco">→ {a.recommendation}</div>
            )}
          </div>
        ))}
      </div>
    </section>
  )
})
