import { memo } from 'react'
import { useStore } from '../store'
import { DAMAGE_SAT_PCT } from './collapse'

/**
 * D2-9 scene overlay — honest captions layered over the 3D view:
 *  - heat-map legend with PHYSICAL UNITS (% EI stiffness loss on the main span,
 *    matching the deck tint in MorbiBridge — the ramp saturates at 35%)
 *  - labeled deflection exaggeration (deformation is amplified for visibility)
 *  - stale-sensor legend (a node that stopped reporting turns GREY)
 */
export const SceneOverlay = memo(function SceneOverlay() {
  const damagePct = useStore((s) => s.stiffness.damagePct)
  const scenario = useStore((s) => s.scenario)
  const hasHeat = scenario === 'rupture' && damagePct > 0.5

  return (
    <>
      {/* bottom-left: damage heat-map legend (main span only) */}
      <div className={`scene-legend${hasHeat ? ' active' : ''}`}>
        <div className="scene-legend-title">EI stiffness loss · main span</div>
        <div className="scene-legend-bar" />
        <div className="scene-legend-labels">
          <span>0%</span>
          <span>10%</span>
          <span>20%</span>
          <span>{DAMAGE_SAT_PCT}%+</span>
        </div>
        <div className="scene-legend-note">model-inferred · heat tint on deck segments</div>
      </div>

      {/* bottom-right: exaggeration + staleness captions */}
      <div className="scene-captions">
        <div className="scene-caption">
          <span className="scene-caption-dot exag" />
          deformation &amp; mode flex exaggerated for visibility — not to scale
        </div>
        <div className="scene-caption">
          <span className="scene-caption-dot stale" />
          sensor stale = GREY (no data &gt; 4 s)
        </div>
      </div>
    </>
  )
})
