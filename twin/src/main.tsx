import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { connect } from './lib/ws'
import { startStiffnessPolling } from './lib/stiffness'
import { startManifestPolling } from './lib/manifest'
import './styles.css'

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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
