import { memo, useEffect, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { Scenario } from '../store'
import { useStore } from '../store'
import { BRIDGE, deckYAt, resetCollapse, tickCollapse, wobble } from './collapse'

// 2 m deck segments over the 58 m superstructure (14 + 30 + 14).
const SEGS = 29
const SEG_W = BRIDGE.L / SEGS
const deckX = (i: number) => -BRIDGE.half + SEG_W / 2 + i * SEG_W
const WEB_X = BRIDGE.deckW / 2 - 0.17

// Damage tint: main-span segments warm toward amber/red as the measured
// stiffness loss grows; side spans stay near-neutral concrete grey.
function segColor(x: number, damagePct: number): string {
  if (Math.abs(x) > BRIDGE.mainHalf) return '#9aa2ab'
  const d = Math.max(0, Math.min(1, damagePct / 35))
  const t = d * (0.35 + 0.65 * Math.exp(-((x / 7) ** 2)))
  const r = Math.round(0x9a + (0xc2 - 0x9a) * t)
  const g = Math.round(0xa2 - 0x38 * t)
  const b = Math.round(0xab - 0x52 * t)
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`
}

export interface MorbiBridgeProps {
  scenario: Scenario
  collapseEpoch: number
}

/**
 * Parametric Z24 box girder — no downloaded GLB, no cables.
 * 58 m post-tensioned concrete box girder (14 + 30 + 14 m), two interior piers
 * at x = ±14, abutments at ±29, river plane.  Damage arc: mid-span deflection
 * (sag) + exaggerated first-mode flexing (wobble) at the *measured* f1 from
 * the backend physics overlay; main-span segments heat-map toward red with the
 * measured stiffness loss.  Total well under 10k tris.
 */
export const MorbiBridge = memo(function MorbiBridge({
  scenario,
  collapseEpoch,
}: MorbiBridgeProps) {
  const topRefs = useRef<Array<THREE.Mesh | null>>([])
  const botRefs = useRef<Array<THREE.Mesh | null>>([])
  const webRefs = useRef<Array<THREE.Mesh | null>>([])
  const matRefs = useRef<Array<THREE.MeshStandardMaterial | null>>([])
  const pierARef = useRef<THREE.Mesh>(null)
  const pierBRef = useRef<THREE.Mesh>(null)

  // Re-mount the arc clock on collapse replay.
  useEffect(() => {
    resetCollapse()
  }, [collapseEpoch])

  useFrame((state, delta) => {
    tickCollapse(scenario, delta)
    const t = state.clock.elapsedTime
    const damagePct = useStore.getState().stiffness.damagePct
    const crack = scenario === 'rupture' ? 1 : 0

    for (let i = 0; i < SEGS; i++) {
      const x = deckX(i)
      const y = deckYAt(x) + wobble(x, t)
      const top = topRefs.current[i]
      const bot = botRefs.current[i]
      const webA = webRefs.current[i * 2]
      const webB = webRefs.current[i * 2 + 1]
      if (top) top.position.set(x, y + BRIDGE.deckH / 2, 0)
      if (bot) bot.position.set(x, y - BRIDGE.deckH / 2, 0)
      if (webA) {
        webA.position.set(x, y, WEB_X)
        webA.rotation.z = 0.012 * Math.sin(t * 2.0) * crack
      }
      if (webB) {
        webB.position.set(x, y, -WEB_X)
        webB.rotation.z = -0.012 * Math.sin(t * 2.0) * crack
      }
      // per-frame damage heat tint (reads the overlay, no re-render)
      const mat = matRefs.current[i]
      if (mat) mat.color.set(segColor(x, damagePct))
    }

    // pier sway follows the deck so the bearing interface never detaches
    const sway = 0.02 * Math.sin(t * 2.0) * crack
    if (pierARef.current) pierARef.current.rotation.z = sway
    if (pierBRef.current) pierBRef.current.rotation.z = -sway
  })

  return (
    <group>
      {Array.from({ length: SEGS }, (_, i) => {
        const x = deckX(i)
        const base = BRIDGE.deckY
        return (
          <group key={i}>
            <mesh ref={(el) => { topRefs.current[i] = el }} position={[x, base + BRIDGE.deckH / 2, 0]}>
              <boxGeometry args={[SEG_W, 0.28, BRIDGE.deckW]} />
              <meshStandardMaterial
                ref={(el) => { matRefs.current[i] = el }}
                color={segColor(x, 0)}
                roughness={0.85}
                metalness={0.05}
              />
            </mesh>
            <mesh ref={(el) => { botRefs.current[i] = el }} position={[x, base - BRIDGE.deckH / 2, 0]}>
              <boxGeometry args={[SEG_W, 0.24, BRIDGE.deckW]} />
              <meshStandardMaterial color="#8d959d" roughness={0.9} metalness={0.05} />
            </mesh>
            <mesh ref={(el) => { webRefs.current[i * 2] = el }} position={[x, base, WEB_X]}>
              <boxGeometry args={[SEG_W, BRIDGE.deckH - 0.52, 0.34]} />
              <meshStandardMaterial color="#8d959d" roughness={0.9} metalness={0.05} />
            </mesh>
            <mesh ref={(el) => { webRefs.current[i * 2 + 1] = el }} position={[x, base, -WEB_X]}>
              <boxGeometry args={[SEG_W, BRIDGE.deckH - 0.52, 0.34]} />
              <meshStandardMaterial color="#8d959d" roughness={0.9} metalness={0.05} />
            </mesh>
          </group>
        )
      })}

      {/* interior piers at x = ±14 */}
      <mesh ref={pierARef} position={[-BRIDGE.pierX, (BRIDGE.deckY - 2.4) / 2, 0]}>
        <boxGeometry args={[1.1, BRIDGE.deckY - 2.4, 4.4]} />
        <meshStandardMaterial color="#7c858d" roughness={0.8} metalness={0.1} />
      </mesh>
      <mesh ref={pierBRef} position={[BRIDGE.pierX, (BRIDGE.deckY - 2.4) / 2, 0]}>
        <boxGeometry args={[1.1, BRIDGE.deckY - 2.4, 4.4]} />
        <meshStandardMaterial color="#7c858d" roughness={0.8} metalness={0.1} />
      </mesh>

      {/* abutments at ±29 */}
      <mesh position={[-BRIDGE.half - 2.5, (BRIDGE.deckY - 2.4) / 2, 0]}>
        <boxGeometry args={[5, BRIDGE.deckY - 2.4, 8]} />
        <meshStandardMaterial color="#5d666e" roughness={0.9} metalness={0.05} />
      </mesh>
      <mesh position={[BRIDGE.half + 2.5, (BRIDGE.deckY - 2.4) / 2, 0]}>
        <boxGeometry args={[5, BRIDGE.deckY - 2.4, 8]} />
        <meshStandardMaterial color="#5d666e" roughness={0.9} metalness={0.05} />
      </mesh>

      {/* river */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.4, -30]}>
        <planeGeometry args={[300, 240]} />
        <meshStandardMaterial color="#3b7ea0" roughness={0.95} />
      </mesh>
    </group>
  )
})
