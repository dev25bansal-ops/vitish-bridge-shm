import { useState } from 'react'
import { TwinCanvas } from './scene/TwinCanvas'
import { BridgeMap } from './map/BridgeMap'
import { HealthPanel } from './panels/HealthPanel'
import { AlertsPanel } from './panels/AlertsPanel'
import { CopilotPanel } from './panels/CopilotPanel'
import { ProvenancePanel } from './panels/ProvenancePanel'
import { SourceBadge, StoryControls } from './panels/StoryControls'
import { useStore } from './store'

export default function App() {
  const [showMap, setShowMap] = useState(true)
  const selectedBridgeId = useStore((s) => s.selectedBridgeId)
  const bridges = useStore((s) => s.bridges)
  const liveBhi = useStore((s) => s.live.bhi)

  const selected = bridges.find((b) => b.id === selectedBridgeId)

  return (
    <div className="hud">
      <header className="hud-top">
        <div className="brand">
          VITISH SHM <span className="brand-accent">· Bridge Health</span>
        </div>
        <div className="top-meta">
          {selected ? (
            <>
              <span className="top-name">{selected.name}</span>
              <span className="top-id">{selected.id}</span>
            </>
          ) : (
            <span className="top-name">—</span>
          )}
          <span className="top-bhi">
            BHI <strong>{liveBhi.toFixed(1)}</strong>
          </span>
        </div>
        <div className="top-right">
          <SourceBadge />
          <span className="top-window">window 10.24 s · fs 100 Hz</span>
        </div>
      </header>

      <div className={`hud-body${showMap ? '' : ' no-map'}`}>
        {showMap && (
          <aside className="hud-left">
            <BridgeMap />
          </aside>
        )}
        <main className="hud-center">
          <TwinCanvas />
        </main>
        <aside className="hud-right">
          <HealthPanel />
          <AlertsPanel />
          <CopilotPanel />
          <ProvenancePanel />
        </aside>
      </div>

      <footer className="hud-bottom">
        <StoryControls onToggleMap={() => setShowMap((v) => !v)} />
      </footer>
    </div>
  )
}
