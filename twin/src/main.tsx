import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { connect } from './lib/ws'
import './styles.css'

// One-shot: try the live WebSocket bridge; fall back to offline replay on
// connect failure or after a 3 s timeout (see lib/ws.ts).
connect()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
