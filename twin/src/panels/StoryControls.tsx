import { memo } from 'react'
import { useStore } from '../store'
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
}

/** Storyboard controls: drive the collapse scenario + map visibility. */
export const StoryControls = memo(function StoryControls({ onToggleMap }: StoryControlsProps) {
  const scenario = useStore((s) => s.scenario)
  const setScenario = useStore((s) => s.setScenario)
  const replayCollapse = useStore((s) => s.replayCollapse)
  const stiffness = useStore((s) => s.stiffness)

  // Honest narrative per data path.  The offline replay synthesizes a modal
  // f1 drop (3.8 -> 3.5 Hz) so the overlay shows "f1 falling"; the live Z24
  // path's rupture is a forced 4 Hz tonal that does NOT shift the modal f1, so
  // the overlay honestly reads "vibration anomaly" instead of a stiffness drop.
  const f1Dropped =
    stiffness.damagePct > 5 ||
    (stiffness.f1Meas > 0 && stiffness.f1Meas < stiffness.f1Ref * 0.97)
  const hint =
    scenario === 'rupture'
      ? f1Dropped
        ? 'STIFFNESS-LOSS ARC ACTIVE · f1 falling'
        : 'VIBRATION ANOMALY · forced 4 Hz signature active'
      : `SYSTEM NOMINAL · f1 ${stiffness.f1Meas ? stiffness.f1Meas.toFixed(1) : 3.8} Hz`

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
      </div>
      <div className={`scenario-hint ${scenario === 'rupture' ? 'rupture' : ''}`}>
        {hint}
      </div>
    </div>
  )
})

export type { WsStatus }
