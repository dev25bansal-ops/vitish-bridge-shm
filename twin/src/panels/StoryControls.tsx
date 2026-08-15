import { memo } from 'react'
import { useStore, F1_REF_HZ } from '../store'
import type { WsStatus } from '../store'

/** LIVE vs REPLAY badge — the honesty feature: every data source is labeled. */
export function SourceBadge() {
  const wsStatus = useStore((s) => s.wsStatus)
  const label =
    wsStatus === 'live'
      ? 'LIVE · backend ws'
      : wsStatus === 'replay'
        ? 'REPLAY · offline fixtures'
        : 'CONNECTING…'
  return (
    <div className={`source-badge status-${wsStatus}`}>
      <span className="dot" />
      {label}
    </div>
  )
}

interface StoryControlsProps {
  onToggleMap: () => void
  geoView: boolean
  onToggleGeo: () => void
}

/** Storyboard controls: drive the collapse scenario + map/geo view visibility. */
export const StoryControls = memo(function StoryControls({
  onToggleMap,
  geoView,
  onToggleGeo,
}: StoryControlsProps) {
  const scenario = useStore((s) => s.scenario)
  const setScenario = useStore((s) => s.setScenario)
  const replayCollapse = useStore((s) => s.replayCollapse)
  const stiffness = useStore((s) => s.stiffness)
  const seeded = useStore((s) => s.seededDefect)

  // Honest narrative per data path.  D2-12: the rupture arc is a SEEDED Z24
  // defect (EI reduced in a named span zone -> the FEM first mode f1 slides
  // 3.80 -> ~3.2 Hz), so the overlay reads a real stiffness loss with the exact
  // defect label + seeded EI %.  No forced tonal in the modern path.
  const f1Dropped =
    stiffness.damagePct > 5 ||
    (stiffness.f1Meas > 0 && stiffness.f1Meas < stiffness.f1Ref * 0.97)
  const seededActive = seeded.label && seeded.label !== 'none'
  const hint =
    scenario === 'rupture'
      ? seededActive
        ? `SEEDED Z24 DEFECT · ${seeded.label.toUpperCase()} · EI -${Math.round(seeded.eiLossPct)}% · f1 ${seeded.f1Ref.toFixed(2)} -> ${seeded.f1.toFixed(2)} Hz`
        : f1Dropped
          ? 'STIFFNESS-LOSS ARC ACTIVE · f1 falling'
          : 'VIBRATION ANOMALY · broadband signature active'
      : `SYSTEM NOMINAL · f1 ${stiffness.f1Meas ? stiffness.f1Meas.toFixed(1) : F1_REF_HZ} Hz`

  return (
    <div className="story-controls">
      <SourceBadge />
      <div className="scenario-buttons">
        <button
          className={`story-btn${scenario === 'rupture' ? ' active rupture' : ''}`}
          onClick={replayCollapse}
          title="Replay the stiffness-loss story arc from the start"
        >
          ▶ Replay damage arc
        </button>
        <button
          className={`story-btn${scenario === 'healthy' ? ' active' : ''}`}
          onClick={() => setScenario('healthy')}
        >
          Healthy
        </button>
        <button
          className={`story-btn${scenario === 'rupture' ? ' active rupture' : ''}`}
          onClick={() => setScenario('rupture')}
        >
          Rupture
        </button>
        <button className="story-btn" onClick={onToggleMap}>
          Toggle map
        </button>
        <button
          className={`story-btn${geoView ? ' active' : ''}`}
          onClick={onToggleGeo}
          title="Real terrain + Google Photorealistic 3D Tiles at the Z24 reference site (Cesium ion)"
        >
          {geoView ? '3D view' : 'Geo view'}
        </button>
      </div>
      <div className={`scenario-hint ${scenario === 'rupture' ? 'rupture' : ''}`}>
        {hint}
      </div>
    </div>
  )
})

export type { WsStatus }
