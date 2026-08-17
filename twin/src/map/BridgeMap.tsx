import { memo, useEffect, useRef, useState } from 'react'
import { Map as MapLibreMap, NavigationControl, AttributionControl } from 'maplibre-gl'
import type { GeoJSONSource } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useStore } from '../store'
import type { TwinState } from '../store'
import { stateHex, STATE_COLORS, ACCENT } from '../lib/theme'
import { matchStateColor } from '../lib/mapStyle'
import { FleetPriorityPanel } from './FleetPriorityPanel'

// OpenFreeMap public tiles — no API key. If they fail to load (offline), we
// fall back to an inline SVG projection so the map still works with no network.
const TILE_STYLE = 'https://tiles.openfreemap.org/styles/positron'
const FALLBACK_TIMEOUT_MS = 6000

interface GFeature {
  type: 'Feature'
  properties: { id: string; name: string; state: string; bhi: number }
  geometry: { type: 'Point'; coordinates: [number, number] }
}

interface GFeatureCollection {
  type: 'FeatureCollection'
  features: GFeature[]
}

function buildGeoJSON(state: TwinState): GFeatureCollection {
  const features = state.bridges.map((b) => {
    const isHero = b.id === 'z24'
    return {
      type: 'Feature' as const,
      properties: {
        id: b.id,
        name: b.name,
        state: isHero ? state.live.state : b.state,
        bhi: isHero ? state.live.bhi : b.bhi,
      },
      geometry: { type: 'Point' as const, coordinates: [b.lng, b.lat] as [number, number] },
    }
  })
  return { type: 'FeatureCollection', features }
}

function SvgFallback({
  selectedId,
}: {
  selectedId: string
}) {
  const bridges = useStore((s) => s.bridges)
  const liveState = useStore((s) => s.live.state)
  const setSelectedBridgeId = useStore((s) => s.setSelectedBridgeId)
  const boxRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 320, h: 420 })

  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const { w, h } = size
  const pad = 26
  let minLng = Infinity
  let maxLng = -Infinity
  let minLat = Infinity
  let maxLat = -Infinity
  for (const b of bridges) {
    minLng = Math.min(minLng, b.lng)
    maxLng = Math.max(maxLng, b.lng)
    minLat = Math.min(minLat, b.lat)
    maxLat = Math.max(maxLat, b.lat)
  }
  if (!Number.isFinite(minLng)) {
    minLng = -125
    maxLng = -66
    minLat = 24
    maxLat = 50
  }
  const spanLng = Math.max(1e-6, maxLng - minLng)
  const spanLat = Math.max(1e-6, maxLat - minLat)
  const px = (lng: number) => pad + ((lng - minLng) / spanLng) * (w - pad * 2)
  const py = (lat: number) => pad + ((maxLat - lat) / spanLat) * (h - pad * 2)

  const gridStepX = Math.max(1, Math.floor((w - pad * 2) / 4))
  const gridStepY = Math.max(1, Math.floor((h - pad * 2) / 5))

  return (
    <div ref={boxRef} className="map-fallback">
      <svg width="100%" height="100%" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Fleet map (offline SVG)">
        <rect x={0} y={0} width={w} height={h} fill="var(--bg)" />
        {Array.from({ length: 5 }, (_, i) => {
          const x = pad + i * gridStepX
          return <line key={`v${i}`} x1={x} y1={pad} x2={x} y2={h - pad} stroke="var(--grid)" strokeWidth={1} />
        })}
        {Array.from({ length: 6 }, (_, i) => {
          const y = pad + i * gridStepY
          return <line key={`h${i}`} x1={pad} y1={y} x2={w - pad} y2={y} stroke="var(--grid)" strokeWidth={1} />
        })}
        {bridges.map((b) => {
          const isHero = b.id === 'z24'
          const state = isHero ? liveState : b.state
          const isSel = b.id === selectedId
          const cx = px(b.lng)
          const cy = py(b.lat)
          return (
            <g
              key={b.id}
              role="button"
              onClick={() => setSelectedBridgeId(b.id)}
              className="svg-point"
            >
              {isSel && <circle cx={cx} cy={cy} r={9} fill="none" stroke={ACCENT} strokeWidth={1.5} />}
              <circle cx={cx} cy={cy} r={isHero ? 6 : 4} fill={stateHex(state)} stroke="var(--panel)" strokeWidth={1.5} />
              {isHero && <circle cx={cx} cy={cy} r={11} fill="none" stroke={stateHex(state)} strokeOpacity={0.45} strokeWidth={1.5} />}
            </g>
          )
        })}
      </svg>
      <div className="map-badge">OFFLINE MAP · SVG fallback</div>
      <div className="map-legend">
        {(['GREEN', 'AMBER', 'RED'] as const).map((s) => (
          <span key={s}>
            <span className="legend-dot" style={{ background: STATE_COLORS[s] }} />{s}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Live MapLibre map of the 50-bridge fleet, data-driven fill by BHI state. */
export const BridgeMap = memo(function BridgeMap() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [fallback, setFallback] = useState(false)
  const selectedId = useStore((s) => s.selectedBridgeId)
  const setSelectedBridgeId = useStore((s) => s.setSelectedBridgeId)

  useEffect(() => {
    if (fallback) return
    const el = containerRef.current
    if (!el) return

    let map: MapLibreMap | null = null
    try {
      map = new MapLibreMap({
        container: el,
        style: TILE_STYLE,
        center: [-98, 39],
        zoom: 3.2,
        attributionControl: false,
      })
    } catch {
      setFallback(true)
      return
    }

    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new AttributionControl({ compact: true }), 'bottom-right')

    const ok = { loaded: false }
    const timer = window.setTimeout(() => {
      if (!ok.loaded) setFallback(true)
    }, FALLBACK_TIMEOUT_MS)

    const onError = () => {
      if (!ok.loaded) setFallback(true)
    }
    map.on('error', onError)

    let sourceAdded = false
    const addSource = () => {
      if (sourceAdded || !map) return
      sourceAdded = true
      map.addSource('bridges', { type: 'geojson', data: buildGeoJSON(useStore.getState()) as never })
      map.addLayer({
        id: 'bridges-fill',
        type: 'fill',
        source: 'bridges',
        paint: {
          'fill-color': matchStateColor(),
          'fill-opacity': 0.18,
        },
      })
      map.addLayer({
        id: 'bridges-ring',
        type: 'circle',
        source: 'bridges',
        paint: {
          'circle-radius': 5,
          'circle-color': matchStateColor(),
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.5,
        },
      })
      map.on('click', 'bridges-ring', (e) => {
        const id = e.features?.[0]?.properties?.id
        if (typeof id === 'string') setSelectedBridgeId(id)
      })
      map.on('mouseenter', 'bridges-ring', () => {
        if (map) map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', 'bridges-ring', () => {
        if (map) map.getCanvas().style.cursor = ''
      })
    }

    map.on('load', () => {
      ok.loaded = true
      addSource()
      // Fit the whole fleet (49 US regulators + the Swiss Z24 hero) so the
      // hero pin at the A1 near Koppigen is never off-screen — mirrors the
      // offline SVG fallback's auto-fit, keeping the two map modes consistent.
      const bs = useStore.getState().bridges
      if (bs.length > 0) {
        let minLng = Infinity
        let maxLng = -Infinity
        let minLat = Infinity
        let maxLat = -Infinity
        for (const b of bs) {
          minLng = Math.min(minLng, b.lng)
          maxLng = Math.max(maxLng, b.lng)
          minLat = Math.min(minLat, b.lat)
          maxLat = Math.max(maxLat, b.lat)
        }
        if (Number.isFinite(minLng)) {
          map?.fitBounds(
            [
              [minLng, minLat],
              [maxLng, maxLat],
            ],
            { padding: 36, duration: 0 },
          )
        }
      }
    })

    const unsub = useStore.subscribe((state) => {
      if (!sourceAdded || !map) return
      const src = map.getSource('bridges') as GeoJSONSource | undefined
      if (src) src.setData(buildGeoJSON(state) as never)
    })

    return () => {
      window.clearTimeout(timer)
      unsub()
      map?.remove()
    }
  }, [fallback, setSelectedBridgeId])

  return (
    <div className="map-shell">
      {fallback ? (
        <SvgFallback selectedId={selectedId} />
      ) : (
        <div ref={containerRef} className="map-canvas" />
      )}
      {/* S1: the fleet-priority card overlays both map modes (MapLibre and the
          offline SVG fallback) so the RUL decision surface is always on. */}
      <FleetPriorityPanel />
      <div className="map-title">Fleet · 50 bridges</div>
    </div>
  )
})
