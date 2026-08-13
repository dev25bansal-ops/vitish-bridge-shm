import { memo, useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { Scenario } from '../store'
import { useStore } from '../store'
import {
  BRIDGE,
  cableYAt,
  collapseState,
  deckYAt,
  resetCollapse,
  tickCollapse,
  wobble,
} from './collapse'

const DECK_SEGS = 23
const SEG_W = BRIDGE.L / DECK_SEGS // 10 m
const HANGER_SPAN = 19 // 19 hanger stations, one per 10 m along the main span
const HANGER_COUNT = HANGER_SPAN * 2 // both sides
const CABLE_SEGS = 64

const deckX = (i: number) => -BRIDGE.half + SEG_W / 2 + i * SEG_W

// Pre-allocated scratch (no per-frame allocation in the hot loop).
const cablePtsA = Array.from({ length: CABLE_SEGS + 1 }, () => new THREE.Vector3())
const cablePtsB = Array.from({ length: CABLE_SEGS + 1 }, () => new THREE.Vector3())
const IDENT_Q = new THREE.Quaternion()
const tmpM = new THREE.Matrix4()
const tmpP = new THREE.Vector3()
const tmpS = new THREE.Vector3()

function buildCableGeometry(zSide: number, t: number, pts: THREE.Vector3[]): THREE.TubeGeometry {
  for (let i = 0; i <= CABLE_SEGS; i++) {
    const x = -BRIDGE.anchorX + (2 * BRIDGE.anchorX * i) / CABLE_SEGS
    pts[i].set(x, cableYAt(x) + wobble(x, t), zSide)
  }
  const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal', 0.5)
  return new THREE.TubeGeometry(curve, CABLE_SEGS * 2, 0.34, 8, false)
}

export interface MorbiBridgeProps {
  scenario: Scenario
  collapseEpoch: number
  /** Optional static override of the collapse state (storyboard-driven). */
  collapse?: {
    cableBroken: boolean
    sag: number
    cascade: number
  }
}

/**
 * Parametric suspension bridge — no downloaded GLB.
 * Deck 230 x 1.25 (BoxGeometry segments), 2 towers, catenary main cables
 * (TubeGeometry along a CatmullRomCurve3), instanced hangers, piers, river.
 * Total is well under 10k tris.
 */
export const MorbiBridge = memo(function MorbiBridge({
  scenario,
  collapseEpoch,
  collapse,
}: MorbiBridgeProps) {
  const deckRefs = useRef<Array<THREE.Mesh | null>>([])
  const cableARef = useRef<THREE.Mesh>(null)
  const cableBRef = useRef<THREE.Mesh>(null)
  const hangerRef = useRef<THREE.InstancedMesh>(null)
  const towerARef = useRef<THREE.Mesh>(null)
  const towerBRef = useRef<THREE.Mesh>(null)
  const cableGeoA = useRef<THREE.BufferGeometry | null>(null)
  const cableGeoB = useRef<THREE.BufferGeometry | null>(null)

  const hangerXs = useMemo(() => Array.from({ length: HANGER_SPAN }, (_, i) => -90 + i * 10), [])

  // Initial cable shapes so the meshes render before the first frame.
  const [geoA, geoB] = useMemo(() => {
    const a = buildCableGeometry(-BRIDGE.zCable, 0, cablePtsA)
    const b = buildCableGeometry(BRIDGE.zCable, 0, cablePtsB)
    cableGeoA.current = a
    cableGeoB.current = b
    return [a, b]
  }, [])

  useEffect(() => {
    resetCollapse()
  }, [collapseEpoch])

  useFrame((state, delta) => {
    tickCollapse(scenario, delta)
    const t = state.clock.elapsedTime
    // `collapse` is an optional static override for storyboards; when absent the
    // internal clock (driven by scenario) is authoritative via collapseState.
    const cascade = collapse ? collapse.cascade : collapseState.cascade

    // deck segments — vertical droop + subtle torsion during cascade
    for (let i = 0; i < DECK_SEGS; i++) {
      const m = deckRefs.current[i]
      if (!m) continue
      const x = deckX(i)
      m.position.y = deckYAt(x) + wobble(x, t)
      m.rotation.z = Math.sin(t * 2.1) * 0.018 * cascade * (x / BRIDGE.half)
    }

    // main cables — rebuild the TubeGeometry from the live curve (small; ~2k tris)
    if (cableARef.current) {
      cableGeoA.current?.dispose()
      cableGeoA.current = buildCableGeometry(-BRIDGE.zCable, t, cablePtsA)
      cableARef.current.geometry = cableGeoA.current
    }
    if (cableBRef.current) {
      cableGeoB.current?.dispose()
      cableGeoB.current = buildCableGeometry(BRIDGE.zCable, t, cablePtsB)
      cableBRef.current.geometry = cableGeoB.current
    }

    // tower sway
    const sway = Math.sin(t * 1.7) * 0.03 * cascade
    if (towerARef.current) towerARef.current.rotation.z = sway
    if (towerBRef.current) towerBRef.current.rotation.z = sway

    // hangers — instanced vertical struts from cable to deck
    const hm = hangerRef.current
    if (hm) {
      let idx = 0
      for (const x of hangerXs) {
        const top = cableYAt(x) + wobble(x, t)
        const bot = deckYAt(x) + wobble(x, t)
        const len = Math.max(0.05, top - bot)
        const mid = (top + bot) / 2
        tmpP.set(0, 0, 0)
        tmpS.set(1, len, 1)
        for (const side of [-1, 1]) {
          tmpP.set(x, mid, side * BRIDGE.zDeck)
          tmpM.compose(tmpP, IDENT_Q, tmpS)
          hm.setMatrixAt(idx++, tmpM)
        }
      }
      hm.instanceMatrix.needsUpdate = true
    }
  })

  return (
    <group>
      {/* deck */}
      {Array.from({ length: DECK_SEGS }, (_, i) => (
        <mesh key={i} ref={(el) => { deckRefs.current[i] = el }} position={[deckX(i), BRIDGE.deckY, 0]}>
          <boxGeometry args={[SEG_W, 1.25, 9]} />
          <meshStandardMaterial color="#3d454e" roughness={0.85} metalness={0.1} />
        </mesh>
      ))}

      {/* towers */}
      <mesh ref={towerARef} position={[-BRIDGE.towerX, 22, 0]}>
        <boxGeometry args={[7, 44, 7]} />
        <meshStandardMaterial color="#2f363e" roughness={0.7} metalness={0.3} />
      </mesh>
      <mesh ref={towerBRef} position={[BRIDGE.towerX, 22, 0]}>
        <boxGeometry args={[7, 44, 7]} />
        <meshStandardMaterial color="#2f363e" roughness={0.7} metalness={0.3} />
      </mesh>
      <mesh position={[-BRIDGE.towerX, 45.5, 0]}>
        <boxGeometry args={[9, 3, 9]} />
        <meshStandardMaterial color="#39424c" roughness={0.8} />
      </mesh>
      <mesh position={[BRIDGE.towerX, 45.5, 0]}>
        <boxGeometry args={[9, 3, 9]} />
        <meshStandardMaterial color="#39424c" roughness={0.8} />
      </mesh>

      {/* main cables */}
      <mesh ref={cableARef} geometry={geoA}>
        <meshStandardMaterial color="#4a5158" roughness={0.5} metalness={0.6} />
      </mesh>
      <mesh ref={cableBRef} geometry={geoB}>
        <meshStandardMaterial color="#4a5158" roughness={0.5} metalness={0.6} />
      </mesh>

      {/* hangers */}
      <instancedMesh ref={hangerRef} args={[undefined, undefined, HANGER_COUNT]}>
        <cylinderGeometry args={[0.09, 0.09, 1, 6, 1, true]} />
        <meshStandardMaterial color="#8b96a1" roughness={0.6} metalness={0.4} />
      </instancedMesh>

      {/* piers under towers */}
      <mesh position={[-BRIDGE.towerX, 7, 0]}>
        <cylinderGeometry args={[3, 3.4, 14, 10]} />
        <meshStandardMaterial color="#37404a" roughness={0.8} />
      </mesh>
      <mesh position={[BRIDGE.towerX, 7, 0]}>
        <cylinderGeometry args={[3, 3.4, 14, 10]} />
        <meshStandardMaterial color="#37404a" roughness={0.8} />
      </mesh>

      {/* abutments */}
      <mesh position={[-BRIDGE.half - 3, 7, 0]}>
        <boxGeometry args={[8, 14, 10]} />
        <meshStandardMaterial color="#2b323a" roughness={0.85} />
      </mesh>
      <mesh position={[BRIDGE.half + 3, 7, 0]}>
        <boxGeometry args={[8, 14, 10]} />
        <meshStandardMaterial color="#2b323a" roughness={0.85} />
      </mesh>

      {/* river */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.6, -60]}>
        <planeGeometry args={[1000, 720]} />
        <meshStandardMaterial color="#0b131c" roughness={0.95} />
      </mesh>
    </group>
  )
})
