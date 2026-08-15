import { useState } from 'react'
import { TwinCanvas } from './scene/TwinCanvas'
import { SceneOverlay } from './scene/SceneOverlay'
import { GeoContext } from './scene/GeoContext'
import { BridgeMap } from './map/BridgeMap'
import { HealthPanel } from './panels/HealthPanel'
import { DeteriorationPanel } from './panels/DeteriorationPanel'
import { AlertsPanel } from './panels/AlertsPanel'
import { CopilotPanel } from './panels/CopilotPanel'
import { ProvenancePanel } from './panels/ProvenancePanel'
import { SimClockBadge } from './panels/SimClockBadge'
import { SourceBadge, StoryControls } from './panels/StoryControls'
import { ErrorBoundary } from './ErrorBoundary'
import { useStore, WINDOW_LABEL } from './store'

export default function App() {
  const [showMap, setShowMap] = useState(true)
  const [geoView, setGeoView] = useState(false)
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
          <SimClockBadge />
          <span className="top-window">{WINDOW_LABEL}</span>
        </div>
      </header>

      <ErrorBoundary label="main view">
        <div className={`hud-body${showMap ? '' : ' no-map'}`}>
          {showMap && (
            <aside className="hud-left">
              <BridgeMap />
            </aside>
          )}
          <main className="hud-center">
            {geoView ? (
              <GeoContext />
            ) : (
              <>
                <TwinCanvas />
                <SceneOverlay />
              </>
            )}
          </main>
          <aside className="hud-right">
            <HealthPanel />
            <DeteriorationPanel />
            <AlertsPanel />
            <CopilotPanel />
            <ProvenancePanel />
          </aside>
        </div>
      </ErrorBoundary>

      <footer className="hud-bottom">
        <StoryControls
          onToggleMap={() => setShowMap((v) => !v)}
          geoView={geoView}
          onToggleGeo={() => setGeoView((v) => !v)}
        />
      </footer>
    </div>
  )
}
