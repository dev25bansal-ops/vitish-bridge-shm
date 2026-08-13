import { memo, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useStore } from '../store'
import { BRIDGE, deckYAt, wobble } from './collapse'

/**
 * ONE drei Html popup, repositioned every frame under the selected sensor.
 * Shows live node stats + a 256-point Recharts spectrum of the accel window.
 */
export const SensorPopup = memo(function SensorPopup() {
  const sensorId = useStore((s) => s.selectedSensorId)
  const sensors = useStore((s) => s.sensors)
  const spectrum = useStore((s) => s.spectrum)
  const live = useStore((s) => s.live)
  const groupRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    const g = groupRef.current
    if (!g) return
    if (sensorId == null) return
    const sensor = sensors[sensorId]
    if (!sensor) return
    const t = state.clock.elapsedTime
    const offset = sensor.y - BRIDGE.deckY
    g.position.set(sensor.x, deckYAt(sensor.x) + wobble(sensor.x, t) + offset + 2.2, sensor.z)
  })

  const chartData = useMemo(
    () => spectrum.map((v, k) => ({ k, v })),
    [spectrum],
  )

  if (sensorId == null) return null
  const sensor = sensors[sensorId]
  if (!sensor) return null

  return (
    <group ref={groupRef}>
      <Html position={[0, 0, 0]} center zIndexRange={[30, 20]} style={{ pointerEvents: 'none' }}>
        <div className="popup" onClick={(e) => e.stopPropagation()}>
          <div className="popup-head">
            <span className="popup-title">Sensor N{sensor.node}</span>
            <span className={`popup-state ${live.state.toLowerCase()}`}>{live.state}</span>
            <button
              className="popup-close"
              aria-label="Close"
              onClick={() => useStore.getState().setSelectedSensorId(null)}
            >
              ×
            </button>
          </div>
          <div className="popup-stats">
            <div className="stat">
              <span className="stat-label">RMS</span>
              <span className="stat-value">{live.rms.toFixed(3)}</span>
              <span className="stat-unit">m/s²</span>
            </div>
            <div className="stat">
              <span className="stat-label">BHI</span>
              <span className="stat-value">{live.bhi.toFixed(1)}</span>
              <span className="stat-unit">±{live.u.toFixed(1)}</span>
            </div>
            <div className="stat">
              <span className="stat-label">f0</span>
              <span className="stat-value">{live.freq.toFixed(1)}</span>
              <span className="stat-unit">Hz</span>
            </div>
            <div className="stat">
              <span className="stat-label">FLAG</span>
              <span className={`stat-value ${live.flag === 1 ? 'bad' : ''}`}>{live.flag}</span>
              <span className="stat-unit">edge</span>
            </div>
          </div>
          <div className="popup-chart">
            <div className="popup-chart-title">Spectrum · 256-pt window @ 100 Hz</div>
            {spectrum.length > 0 ? (
              <ResponsiveContainer width="100%" height={92}>
                <AreaChart data={chartData} margin={{ top: 4, right: 2, left: 2, bottom: 0 }}>
                  <defs>
                    <linearGradient id="specGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.6} />
                      <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="k" hide />
                  <YAxis hide domain={[0, 'dataMax']} />
                  <Tooltip
                    contentStyle={{ background: '#10161d', border: '1px solid #22303c', fontSize: 11 }}
                    labelStyle={{ color: '#7c8ea0' }}
                    formatter={(value) => [Number(value ?? 0).toFixed(4), 'mag']}
                  />
                  <Area
                    type="monotone"
                    dataKey="v"
                    stroke="#38bdf8"
                    strokeWidth={1}
                    fill="url(#specGrad)"
                    dot={false}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="popup-chart-empty">awaiting accel data…</div>
            )}
          </div>
        </div>
      </Html>
    </group>
  )
})
