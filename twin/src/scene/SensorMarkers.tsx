import { memo, useLayoutEffect, useRef } from 'react'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import * as THREE from 'three'
import type { HealthState } from '../store'
import { useStore } from '../store'
import { BRIDGE, collapseState, deckYAt, wobble } from './collapse'
import { stateHex } from '../lib/theme'
import { FLEET_COUNT } from '../lib/fixtures'

const SENSOR_COUNT = 3
const TOTAL = SENSOR_COUNT + FLEET_COUNT // 3 visible nodes + 50 fleet markers

const IDENT_Q = new THREE.Quaternion()
const tmpM = new THREE.Matrix4()
const tmpP = new THREE.Vector3()
const tmpS = new THREE.Vector3()
const tmpC = new THREE.Color()

// 50 "regulatory" fleet markers on the water behind the hero bridge (10 x 5).
const fleetPos = new Array<THREE.Vector3>(FLEET_COUNT)
for (let i = 0; i < FLEET_COUNT; i++) {
  const col = i % 10
  const row = Math.floor(i / 10)
  fleetPos[i] = new THREE.Vector3(-135 + col * 30, 1.2, 30 + row * 34)
}

function sensorHealth(i: number): HealthState {
  const st = useStore.getState()
  const { damagePct, eiDriftPct } = st.stiffness
  if (st.scenario !== 'rupture') return 'GREEN'
  // Health tracks the node's own measured evidence, whichever path is live:
  //   offline/replay -> model-inferred stiffness loss (damagePct / EI drift)
  //   live (Z24)      -> measured vibration-anomaly evidence (flag/vib/state);
  //                      the demo's rupture is a forced 4 Hz tonal, not an f1
  //                      drop, so stiffness damage stays ~0 there (honest).
  const liveSev =
    st.live.state === 'RED' ? 40 : st.live.flag === 1 ? 30 : st.live.vib > 0.35 ? 20 : 0
  // Main-span nodes (|x| < 15) degrade first; side-span nodes lag behind.
  const nearMain = Math.abs(st.sensors[i].x) <= BRIDGE.mainHalf
  const d = Math.max(damagePct, eiDriftPct * 0.5, liveSev)
  if (d < 8) return 'GREEN'
  if (d < 20) return nearMain ? 'AMBER' : 'GREEN'
  if (d < 35) return nearMain ? 'RED' : 'AMBER'
  return 'RED'
}

/**
 * ONE InstancedMesh for all sensors. Per-instance color is derived from health
 * every frame by reading the store; scale pulses on an active anomaly flag.
 */
export const SensorMarkers = memo(function SensorMarkers() {
  const mesh = useRef<THREE.InstancedMesh>(null)
  const sensors = useStore((s) => s.sensors)

  useLayoutEffect(() => {
    const m = mesh.current
    if (!m) return
    const st = useStore.getState()
    for (let i = 0; i < SENSOR_COUNT; i++) {
      m.setColorAt(i, tmpC.set(stateHex(sensorHealth(i))).clone())
    }
    for (let i = SENSOR_COUNT; i < TOTAL; i++) {
      const b = st.bridges[i - SENSOR_COUNT]
      m.setColorAt(i, tmpC.set(stateHex(b ? b.state : 'GREEN')).clone())
    }
    if (m.instanceColor) m.instanceColor.needsUpdate = true
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useFrame((state) => {
    const m = mesh.current
    if (!m) return
    const t = state.clock.elapsedTime
    const st = useStore.getState()
    const live = st.live
    const now = Date.now()
    const pulse =
      live.flag === 1 || live.state === 'RED' ? 1 + 0.3 * Math.abs(Math.sin(t * 6)) : 1

    // visible sensor nodes ride the deck
    for (let i = 0; i < SENSOR_COUNT; i++) {
      const sn = sensors[i]
      const offset = sn.y - BRIDGE.deckY
      const y = deckYAt(sn.x) + wobble(sn.x, t) + offset
      const sway = collapseState.cascade * 0.25 * Math.sin(t * 4 + i * 1.7)
      tmpP.set(sn.x, y, sn.z + sway)
      // D2-9: a node that reported and then went quiet > 4 s turns GREY —
      // never invent a health colour for data we no longer have.
      const seen = st.nodeSeen[sn.node]
      const stale = seen !== undefined && now - seen > 4000
      const scale = 1.35 * pulse * (stale ? 0.85 : 1)
      tmpS.set(scale, scale, scale)
      tmpM.compose(tmpP, IDENT_Q, tmpS)
      m.setMatrixAt(i, tmpM)
      m.setColorAt(i, tmpC.set(stale ? '#9ca3af' : stateHex(sensorHealth(i))))
    }

    // fleet markers
    const bridges = st.bridges
    for (let i = SENSOR_COUNT; i < TOTAL; i++) {
      const j = i - SENSOR_COUNT
      const p = fleetPos[j]
      tmpP.set(p.x, p.y + 0.4 * Math.sin(t * 0.7 + j), p.z)
      tmpS.setScalar(0.55)
      tmpM.compose(tmpP, IDENT_Q, tmpS)
      m.setMatrixAt(i, tmpM)
      const b = bridges[j]
      m.setColorAt(i, tmpC.set(stateHex(b ? b.state : 'GREEN')))
    }

    m.instanceMatrix.needsUpdate = true
    if (m.instanceColor) m.instanceColor.needsUpdate = true
  })

  const onPointerDown = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation()
    const id = e.instanceId
    if (id == null || id < 0) return
    if (id < SENSOR_COUNT) {
      useStore.getState().setSelectedSensorId(id)
    } else {
      const b = useStore.getState().bridges[id - SENSOR_COUNT]
      if (b) useStore.getState().setSelectedBridgeId(b.id)
    }
  }

  return (
    <instancedMesh
      ref={mesh}
      args={[undefined, undefined, TOTAL]}
      onPointerDown={onPointerDown}
      onPointerOver={() => (document.body.style.cursor = 'pointer')}
      onPointerOut={() => (document.body.style.cursor = '')}
    >
      <sphereGeometry args={[0.8, 14, 12]} />
      <meshStandardMaterial color="#ffffff" roughness={0.35} metalness={0.25} />
    </instancedMesh>
  )
})
