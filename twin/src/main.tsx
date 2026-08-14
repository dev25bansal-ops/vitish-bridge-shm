import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { connect } from './lib/ws'
import { startStiffnessPolling } from './lib/stiffness'
import './styles.css'

// One-shot: try the live WebSocket bridge; fall back to offline replay on
// connect failure or after a 3 s timeout (see lib/ws.ts).
connect()

// Physics overlay (f1, EI drift, damage %, mode shapes) — a light REST poll
// independent of the telemetry WS. Falls back silently when the backend is
// down (analytic reference mode keeps the scene honest).
startStiffnessPolling()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
