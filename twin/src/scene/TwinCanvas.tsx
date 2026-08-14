import { useFrame, useThree, Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { useStore } from '../store'
import { MorbiBridge } from './MorbiBridge'
import { SensorMarkers } from './SensorMarkers'
import { SensorPopup } from './SensorPopup'
import { BRIDGE, deckYAt } from './collapse'

/** Slowly moves the orbit target toward the selected sensor (or home). */
function CameraRig() {
  const controls = useThree((s) => s.controls) as unknown as
    | { target: THREE.Vector3 }
    | null
    | undefined
  const sensorId = useStore((s) => s.selectedSensorId)
  const sensors = useStore((s) => s.sensors)

  useFrame(() => {
    if (!controls) return
    const home = new THREE.Vector3(0, 5, 0)
    let target = home
    if (sensorId != null && sensors[sensorId]) {
      const sn = sensors[sensorId]
      target = new THREE.Vector3(
        sn.x,
        deckYAt(sn.x) + (sn.y - BRIDGE.deckY) + 3,
        sn.z,
      )
    }
    controls.target.lerp(target, 0.1)
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
