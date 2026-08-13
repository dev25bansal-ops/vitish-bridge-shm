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

  return (
    <div className="story-controls">
      <SourceBadge />
      <div className="scenario-buttons">
        <button
          className={`story-btn${scenario === 'rupture' ? ' active rupture' : ''}`}
          onClick={replayCollapse}
          title="Replay the cable-break story arc from the start"
        >
          ▶ Replay collapse
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
        {scenario === 'rupture' ? 'CABLE-BREAK STORY ARC ACTIVE' : 'SYSTEM NOMINAL'}
      </div>
    </div>
  )
})

export type { WsStatus }
