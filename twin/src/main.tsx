import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { ErrorBoundary } from './ErrorBoundary'
import { discoverConfig } from './lib/config'
import { connect } from './lib/ws'
import { startStiffnessPolling } from './lib/stiffness'
import { startManifestPolling } from './lib/manifest'
import { startDeteriorationPolling } from './lib/deterioration'
import './styles.css'

// Ask the backend which ports it actually bound (it walks to 8001+/8766+ when
// busy) before opening sockets.  discoverConfig never throws and self-times-out
// at 2.5 s, so an offline start still lands on the localhost defaults and the
// WS bridge falls back to honest replay as before.
async function boot(): Promise<void> {
  await discoverConfig()
  // One-shot: try the live WebSocket bridge; fall back to offline replay on
  // connect failure or after a 3 s timeout (see lib/ws.ts).
  connect()

  // Physics overlay (f1, EI drift, damage %, mode shapes) — a light REST poll
  // independent of the telemetry WS. Falls back silently when the backend is
  // down (analytic reference mode keeps the scene honest).
  startStiffnessPolling()

  // D1-5 data-realism manifest (real vs modeled per channel) — slow poll, honest
  // offline default when the backend is unreachable.
  startManifestPolling()

  // D2-11 LTBP Markov projection (Bayesian-updating condition curve) — slow poll,
  // honest offline default when the backend is unreachable.
  startDeteriorationPolling()
}
void boot()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary label="app">
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
