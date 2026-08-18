import { lazy, Suspense, useEffect, useState } from 'react'
import { TwinCanvas } from './scene/TwinCanvas'
import { SceneOverlay } from './scene/SceneOverlay'
import { HealthPanel } from './panels/HealthPanel'
import { DeteriorationPanel } from './panels/DeteriorationPanel'
import { AlertsPanel } from './panels/AlertsPanel'
import { CopilotPanel } from './panels/CopilotPanel'
import { ProvenancePanel } from './panels/ProvenancePanel'
import { SimClockBadge } from './panels/SimClockBadge'
import { SourceBadge, StoryControls } from './panels/StoryControls'
import { ErrorBoundary } from './ErrorBoundary'
import { useStore, WINDOW_LABEL } from './store'

// PERF-07: code-split the heavy views.  maplibre-gl + Cesium are multi-MB
// dependencies that only matter when the user opens the map or the geo view —
// statically importing BridgeMap pulled maplibre into the initial bundle even
// on the default no-map start.  These lazy chunks are fetched on demand (and
// concurrently with first paint).  The panels (recharts) stay static: they are
// rendered immediately, so splitting them would only add a network round-trip.
const BridgeMap = lazy(() =>
  import('./map/BridgeMap').then((m) => ({ default: m.BridgeMap })),
)
const GeoContext = lazy(() =>
  import('./scene/GeoContextLayout').then((m) => ({ default: m.GeoContext })),
)

// PERF-07: the tabs under the toggle each render a lazy subtree; the map/geo
// chunks are a few hundred KB and load in ~100ms locally, so a labeled
// skeleton keeps the HUD stable while they stream in.
function ViewSkeleton({ label }: { label: string }) {
  return (
    <div className="view-skeleton" role="status" aria-label={`loading ${label}`}>
      <div className="view-skeleton-bar" />
      loading {label}…
    </div>
  )
}

// Small boundary-region clones rendered as the lazy views' suspension fallback
// (each is tiny — a brand line, a footer button — never worth their own chunk).
function BoundaryHeader() {
  const selectedBridgeId = useStore((s) => s.selectedBridgeId)
  const bridges = useStore((s) => s.bridges)
  const liveBhi = useStore((s) => s.live.bhi)
  const selected = bridges.find((b) => b.id === selectedBridgeId)
  return (
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
  )
}

function BoundaryFooter({
  geoView,
  onToggleMap,
  onToggleGeo,
}: {
  geoView: boolean
  onToggleMap: () => void
  onToggleGeo: () => void
}) {
  return (
    <footer className="hud-bottom">
      <StoryControls
        onToggleMap={onToggleMap}
        geoView={geoView}
        onToggleGeo={onToggleGeo}
      />
    </footer>
  )
}

export default function App() {
  const [showMap, setShowMap] = useState(true)
  const [geoView, setGeoView] = useState(false)

  // PERF-07: prefetch the split chunks on first idle — the map/geo lazy chunks
  // are ready before the user reaches the toggle, so toggling never shows a
  // fetch spinner in the demo.
  useEffect(() => {
    const preload = () => {
      void import('./map/BridgeMap')
      void import('./scene/GeoContextLayout')
    }
    const id =
      typeof window.requestIdleCallback !== 'undefined'
        ? window.requestIdleCallback(preload)
        : window.setTimeout(preload, 1000)
    return () =>
      typeof window.requestIdleCallback !== 'undefined'
        ? window.cancelIdleCallback(id as number)
        : window.clearTimeout(id as number)
  }, [])

  return (
    <div className="hud">
      <BoundaryHeader />
      <ErrorBoundary label="main view">
        <div className={`hud-body${showMap ? '' : ' no-map'}`}>
          {showMap && (
            <aside className="hud-left">
              <Suspense fallback={<ViewSkeleton label="fleet map" />}>
                <BridgeMap />
              </Suspense>
            </aside>
          )}
          <main className="hud-center">
            {geoView ? (
              <Suspense fallback={<ViewSkeleton label="geo view" />}>
                <GeoContext />
              </Suspense>
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
      <BoundaryFooter
        geoView={geoView}
        onToggleMap={() => setShowMap((v) => !v)}
        onToggleGeo={() => setGeoView((v) => !v)}
      />
    </div>
  )
}
