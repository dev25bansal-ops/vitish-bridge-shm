import { useEffect, useRef } from 'react'
import { useFrame, useThree, Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { useStore } from '../store'
import { MorbiBridge } from './MorbiBridge'
import { SensorMarkers } from './SensorMarkers'
import { SensorPopup } from './SensorPopup'
import { BRIDGE, deckYAt } from './collapse'

// Module-level scratch vectors — never allocate per frame in the rig.
const _HOME = new THREE.Vector3(0, 5, 0)
const _v = new THREE.Vector3()

type RigControls = {
  target: THREE.Vector3
  addEventListener(type: string, fn: () => void): void
  removeEventListener(type: string, fn: () => void): void
}

/**
 * Slowly moves the orbit target toward the selected sensor (or home).
 * The lerp yields while the user is mid-gesture: OrbitControls dispatches
 * 'start'/'end' around rotate/pan/zoom, and we skip those frames so the rig
 * never yanks the camera out of the user's hand mid-drag.
 */
function CameraRig() {
  const controls = useThree((s) => s.controls) as unknown as RigControls | null | undefined
  const sensorId = useStore((s) => s.selectedSensorId)
  const sensors = useStore((s) => s.sensors)
  const interacting = useRef(false)

  useEffect(() => {
    if (!controls) return
    const start = () => { interacting.current = true }
    const end = () => { interacting.current = false }
    controls.addEventListener('start', start)
    controls.addEventListener('end', end)
    return () => {
      controls.removeEventListener('start', start)
      controls.removeEventListener('end', end)
    }
  }, [controls])

  useFrame(() => {
    if (!controls || interacting.current) return
    if (sensorId != null && sensors[sensorId]) {
      const sn = sensors[sensorId]
      _v.set(sn.x, deckYAt(sn.x) + (sn.y - BRIDGE.deckY) + 3, sn.z)
    } else {
      _v.copy(_HOME)
    }
    controls.target.lerp(_v, 0.1)
  })
  return null
}

export function TwinCanvas() {
  const scenario = useStore((s) => s.scenario)
  const collapseEpoch = useStore((s) => s.collapseEpoch)

  return (
    <Canvas
      dpr={[1, 1.5]}
      shadows={false}
      frameloop="always"
      camera={{ position: [36, 20, 46], fov: 42, near: 0.5, far: 1200 }}
      // Clicking empty 3D space clears the sensor selection (the popup's own
      // close button and the CameraRig follow both re-home on null).
      onPointerMissed={() => useStore.getState().setSelectedSensorId(null)}
    >
      <color attach="background" args={['#dce9f2']} />
      <fog attach="fog" args={['#dce9f2', 160, 520]} />

      <ambientLight intensity={0.75} color="#ffffff" />
      <directionalLight position={[90, 140, 70]} intensity={1.35} color="#fff6e8" />
      <directionalLight position={[-120, 60, -80]} intensity={0.5} color="#d8e8f5" />

      <MorbiBridge scenario={scenario} collapseEpoch={collapseEpoch} />
      <SensorMarkers />
      <SensorPopup />
      <CameraRig />

      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.08}
        target={[0, 5, 0]}
        maxDistance={220}
        minDistance={8}
        maxPolarAngle={Math.PI / 2 - 0.02}
      />
    </Canvas>
  )
}
