// D2-7 georeferenced context view.  Swaps the R3F "engineering view" for a real
// Cesium ion globe at the Z24 reference site (A1 corridor near Koppigen, CH):
// real World Terrain + Google Photorealistic 3D Tiles, with our modeled
// box-girder digital shadow and its sensor nodes georeferenced over the site.
// Honest by construction: the terrain/buildings are real (Cesium ion / Google),
// the Z24 structure is the model, and every caption says exactly that.  Falls
// back to a labeled card if the token is missing or the ion tiles can't be
// reached (offline demo).
//
// Cesium is dynamically imported so the ~30 MB package never touches the initial
// bundle — the globe loads only when the user opens the Geo view.
import { memo, useEffect, useRef, useState } from 'react'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { useStore } from '../store'
import { stateHex } from '../lib/theme'
import {
  GEO_CAMERA,
  GEO_NODE_OFFSETS,
  GEO_READY,
  GEO_TOKEN,
  Z24_BOX,
  Z24_SITE,
} from '../lib/geo'

interface GeoStatus {
  kind: 'loading' | 'ready' | 'failed'
  message: string
}

/** Offset a point along a bearing (meters) — WGS84 flat-Earth approx, plenty for 60 m. */
function offsetDeg(lng: number, lat: number, dxM: number, headingDeg: number) {
  const rad = (headingDeg * Math.PI) / 180
  const dLat = (dxM * Math.cos(rad)) / 111320
  const dLng = (dxM * Math.sin(rad)) / (111320 * Math.cos((lat * Math.PI) / 180))
  return { lng: lng + dLng, lat: lat + dLat }
}

type CesiumModule = typeof import('cesium')

export const GeoContext = memo(function GeoContext() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<GeoStatus>({
    kind: GEO_READY ? 'loading' : 'failed',
    message: GEO_READY ? 'loading real terrain…' : 'Cesium ion token missing (twin/.env).',
  })
  const liveBhi = useStore((s) => s.live.bhi)
  const liveState = useStore((s) => s.live.state)

  useEffect(() => {
    const el = containerRef.current
    if (!el || !GEO_READY || !GEO_TOKEN) return
    const token: string = GEO_TOKEN // narrowed: guard above guarantees a real token

    let cancelled = false
    let viewer: InstanceType<CesiumModule['Viewer']> | null = null
    let unsub: (() => void) | null = null

    ;(async () => {
      try {
        const Cesium = await import('cesium')
        if (cancelled) return
        Cesium.Ion.defaultAccessToken = token

        viewer = new Cesium.Viewer(el, {
          animation: false,
          timeline: false,
          fullscreenButton: false,
          baseLayerPicker: false,
          homeButton: false,
          navigationHelpButton: false,
          sceneModePicker: false,
          geocoder: false,
          infoBox: false,
          selectionIndicator: false,
          // Real terrain (ion World Terrain) under the photorealistic tiles.
          terrain: Cesium.Terrain.fromWorldTerrain(),
        })
        if (cancelled) {
          viewer.destroy()
          return
        }
        // The photorealistic tiles carry their own ground imagery + buildings;
        // drop the default Bing layer so we don't stack imagery underneath.
        viewer.imageryLayers.removeAll()
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#0e1c2c')

        // Google Photorealistic 3D Tiles (real ground + buildings), via ion.
        // Restriction acknowledged: used only with the Google geocoder (ours is off).
        const tileset = await Cesium.createGooglePhotorealistic3DTileset({
          onlyUsingWithGoogleGeocoder: true,
        })
        if (cancelled) return
        viewer.scene.primitives.add(tileset)

        // Dev-only debug hook: expose the Cesium viewer for CDP/browser tests
        // to introspect camera + entity state (never used in a prod bundle).
        if (import.meta.env.DEV) {
          ;(window as unknown as { __geoViewer: InstanceType<CesiumModule['Viewer']> }).__geoViewer = viewer
        }

        const site = Z24_SITE
        // The deck elevation is FIXED above the real ground (see Z24_SITE.height
        // in lib/geo.ts).  We deliberately do NOT sample globe.getHeight() at
        // runtime: it returns garbage (-66 km) for many seconds before the World
        // Terrain tile under the site loads, and then drifts with tile LOD, so
        // the modeled structure stays put at its schematic height and the honest
        // caption ("not to scale") owns the rest.
        const deckH = site.height
        if (import.meta.env.DEV) {
          ;(window as unknown as { __geoAnchor: { deckH: number } }).__geoAnchor = { deckH }
        }
        const position = Cesium.Cartesian3.fromDegrees(site.lng, site.lat, deckH)
        const hpr = Cesium.HeadingPitchRoll.fromDegrees(site.headingDeg, 0, 0)
        const orientation = Cesium.Transforms.headingPitchRollQuaternion(position, hpr)

        // Modeled Z24 box-girder digital shadow, colored by live health.
        const boxEntity = viewer.entities.add({
          position,
          orientation,
          box: {
            dimensions: new Cesium.Cartesian3(Z24_BOX.length, Z24_BOX.width, Z24_BOX.depth),
            material: new Cesium.ColorMaterialProperty(
              Cesium.Color.fromCssColorString(stateHex(liveState)),
            ),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.6),
          },
        })

        // Sensor nodes on the deck (nodes 6/7/8, x = -10/0/+10 m).
        const nodeEntities = GEO_NODE_OFFSETS.map((off) => {
          const p = offsetDeg(site.lng, site.lat, off, site.headingDeg)
          return viewer!.entities.add({
            position: Cesium.Cartesian3.fromDegrees(p.lng, p.lat, deckH + Z24_BOX.depth / 2),
            point: {
              pixelSize: 11,
              color: new Cesium.ConstantProperty(Cesium.Color.fromCssColorString(stateHex(liveState))),
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 1.5,
            },
            label: {
              text: `n${off === -10 ? 6 : off === 0 ? 7 : 8}`,
              font: '11px monospace',
              fillColor: Cesium.Color.WHITE,
              pixelOffset: new Cesium.Cartesian2(0, 14),
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              outlineColor: Cesium.Color.fromCssColorString('#0f172a'),
              outlineWidth: 3,
            },
          })
        })

        // Keep the modeled structure's colour honest & live (driven by BHI state).
        unsub = useStore.subscribe((st, prev) => {
          if (st.live.state === prev.live.state) return
          const c = Cesium.Color.fromCssColorString(stateHex(st.live.state))
          if (boxEntity.box) boxEntity.box.material = new Cesium.ColorMaterialProperty(c)
          for (const n of nodeEntities) if (n.point) n.point.color = new Cesium.ConstantProperty(c)
        })

        // Frame the bridge: fly to an EXPLICIT camera destination computed from
        // the site (not flyTo(entity)), so the framing never depends on the box's
        // bounding sphere or terrain state.  Camera sits `distance` m due south
        // of the deck looking north (heading 0), so the modeled structure is
        // dead-center in frame with the real A1 corridor behind it.
        const camPitchRad = Cesium.Math.toRadians(GEO_CAMERA.pitchDeg)
        const camHoriz = GEO_CAMERA.distance * Math.cos(-camPitchRad) // ~260 m
        const camAlt = deckH + GEO_CAMERA.distance * Math.sin(-camPitchRad) // ~150 m up
        const cam = offsetDeg(site.lng, site.lat, camHoriz, 180)
        viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(cam.lng, cam.lat, camAlt),
          orientation: {
            heading: Cesium.Math.toRadians(GEO_CAMERA.headingDeg),
            pitch: camPitchRad,
            roll: 0,
          },
          duration: 2.4,
        })

        if (!cancelled) setStatus({ kind: 'ready', message: '' })
      } catch (err) {
        console.error('D2-7 geo init failed:', err)
        if (!cancelled) {
          setStatus({
            kind: 'failed',
            message: 'real terrain tiles unreachable (no network / ion token). Use the 3D engineering view.',
          })
        }
      }
    })()

    return () => {
      cancelled = true
      unsub?.()
      unsub = null
      if (viewer) {
        try {
          viewer.destroy()
        } catch {
          /* already torn down */
        }
        viewer = null
      }
    }
    // Mount once; live health colour is kept in sync via the store subscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="geo-shell">
      <div ref={containerRef} className="geo-canvas" />

      <div className="geo-caption">
        <span className="geo-chip geo-chip-title">GEOREFERENCED CONTEXT · DIGITAL SHADOW</span>
        <span className="geo-chip">
          terrain &amp; 3D tiles: <b>real</b> (Cesium ion / Google) · Z24 structure: <b>model</b> · not to scale
        </span>
        <span className="geo-chip">
          BHI <b style={{ color: stateHex(liveState) }}>{liveBhi.toFixed(1)}</b> · {liveState}
        </span>
      </div>

      {status.kind !== 'ready' && (
        <div className="geo-fallback">
          <div className="geo-fallback-title">
            {status.kind === 'loading' ? 'LOADING GEOREFERENCED VIEW…' : 'GEOREFERENCED VIEW UNAVAILABLE'}
          </div>
          <div className="geo-fallback-msg">{status.message}</div>
          {status.kind === 'failed' && (
            <div className="geo-fallback-msg">Switch back to the 3D engineering view to continue the demo.</div>
          )}
        </div>
      )}
    </div>
  )
})
