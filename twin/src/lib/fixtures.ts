// Deterministic offline fixture generator — powers REPLAY mode when the live
// WebSocket bridge is unreachable. Same payload shapes as the contract
// (bridge/z24/accel, /bhi, /alert), so the whole demo runs with NO network.
import { useStore, computeBhi, stateFor } from '../store'
import type { AlertSource, Bridge, HealthState, Severity } from '../store'
import { spectrumMagnitudes } from './fft'

export const FLEET_COUNT = 50

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))
const smooth = (x: number) => x * x * (3 - 2 * x)

// (name, lat, lng) — real-ish US locations for the 50-bridge fleet.
const CITIES: Array<[string, number, number]> = [
  ['NYC East River', 40.78, -73.96],
  ['LA Harbor', 33.74, -118.28],
  ['Chicago Skyway', 41.83, -87.62],
  ['Houston Ship Ch', 29.76, -95.36],
  ['Phoenix Gila', 33.45, -112.07],
  ['Philadelphia Del', 39.95, -75.14],
  ['San Antonio', 29.42, -98.49],
  ['San Diego Bay', 32.72, -117.16],
  ['Dallas Trinity', 32.78, -96.8],
  ['San Jose Creek', 37.34, -121.89],
  ['Austin Colorado', 30.27, -97.74],
  ['Jacksonville StJ', 30.33, -81.66],
  ['Fort Worth', 32.76, -97.33],
  ['Columbus Scioto', 39.96, -83.0],
  ['Charlotte Catawba', 35.23, -80.84],
  ['SF Bay', 37.81, -122.37],
  ['Indianapolis', 39.77, -86.16],
  ['Seattle Duwamish', 47.61, -122.33],
  ['Denver Platte', 39.74, -105.0],
  ['DC Potomac', 38.91, -77.04],
  ['Boston Charles', 42.36, -71.05],
  ['Nashville Cumb', 36.17, -86.78],
  ['El Paso Rio', 31.76, -106.49],
  ['Detroit Rouge', 42.33, -83.05],
  ['OKC Canadian', 35.47, -97.52],
  ['Portland Willam', 45.52, -122.68],
  ['Las Vegas Wash', 36.17, -115.14],
  ['Memphis Miss', 35.15, -90.05],
  ['Louisville Ohio', 38.26, -85.76],
  ['Baltimore Patap', 39.28, -76.61],
  ['Milwaukee Lake', 43.04, -87.91],
  ['Albuquerque', 35.08, -106.65],
  ['Tucson SantaCruz', 32.22, -110.97],
  ['Fresno SanJoaq', 36.74, -119.78],
  ['Sacramento', 38.58, -121.49],
  ['KC Missouri', 39.1, -94.58],
  ['Mesa Salt', 33.42, -111.83],
  ['Atlanta Chattah', 33.75, -84.39],
  ['Omaha Missouri', 41.26, -95.93],
  ['Colo Springs', 38.83, -104.82],
  ['Raleigh Neuse', 35.78, -78.64],
  ['Miami Biscayne', 25.77, -80.19],
  ['Long Beach', 33.77, -118.19],
  ['Va Beach', 36.85, -75.98],
  ['Oakland Bay', 37.8, -122.27],
  ['Minneapolis Miss', 44.98, -93.27],
  ['Tulsa Arkansas', 36.15, -96.0],
  ['Tampa Bay', 27.95, -82.46],
  ['New Orleans Miss', 29.95, -90.07],
  ['Wichita Ark', 37.69, -97.34],
  ['Cleveland Cuyah', 41.5, -81.69],
  ['Bakersfield', 35.37, -119.02],
  ['St Louis Miss', 38.63, -90.2],
  ['Pittsburgh Ohio', 40.44, -80.01],
  ['Cincinnati Ohio', 39.1, -84.51],
  ['Tampa Manatee', 27.63, -82.55],
  ['Fargo Red', 46.88, -96.79],
  ['Boise Boise', 43.62, -116.2],
  ['Spokane SpokaneR', 47.66, -117.42],
  ['Knoxville Tn', 35.96, -83.92],
  ['Little Rock', 34.75, -92.29],
  ['Savannah River', 32.08, -81.09],
]

export function generateFleet(): Bridge[] {
  const rand = mulberry32(777001)
  const pool = CITIES.slice()
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    const a = pool[i]
    pool[i] = pool[j]
    pool[j] = a
  }
  const others: Bridge[] = pool.slice(0, FLEET_COUNT - 1).map(([name, lat, lng], i) => {
    const low = i < 4
    const bhi = Math.round((low ? 36 + rand() * 32 : 58 + rand() * 40) * 10) / 10
    return { id: `b${i + 1}`, name, lat, lng, bhi, state: stateFor(bhi) }
  })
  const hero: Bridge = {
    id: 'z24',
    name: 'Z24 · Box Girder (Swiss reference)',
    lat: 41.59,
    lng: -90.5,
    bhi: 82,
    state: 'GREEN',
  }
  return [hero, ...others]
}

// ---------------------------------------------------------------------------
// Replay engine — emits contract-shaped accel / bhi / alert messages on timers
// and pushes them into the store (same code path as the live WS client).
// ---------------------------------------------------------------------------

let timers: number[] = []

export function startReplay(): () => void {
  stopReplay()
  const store = useStore.getState()
  if (store.bridges.length === 0) {
    useStore.setState({ bridges: generateFleet() })
  }
  useStore.setState({ wsStatus: 'replay' })

  const rand = mulberry32(20260813)
  const fs = 100
  const N = 100
  let tick = 0
  let damageClock = 0 // seconds into the current rupture episode
  let prevScenario: string = 'healthy'

  const pushAlert = (severity: Severity, source: AlertSource, text: string, recommendation?: string) => {
    useStore.getState().pushAlert({ severity, source, text, recommendation })
  }

  const emitAccel = () => {
    const s = useStore.getState()
    const rupture = s.scenario === 'rupture'
    const ph1 = rand() * Math.PI * 2
    const ph2 = rand() * Math.PI * 2
    const ph3 = rand() * Math.PI * 2
    // Z24 box-girder modes: healthy f1 = 3.8 Hz (f2 = 15.2); rupture drops f1
    // toward ~3.5 Hz (mid-span stiffness loss) and adds broadband impact energy.
    const f1 = rupture ? 3.5 : 3.8
    const f2 = 4 * f1
    const amps = rupture
      ? { a1: 0.1, a2: 0.14, a3: 0.3, noise: 0.06, impact: 0.35 }
      : { a1: 0.035, a2: 0.06, a3: 0.012, noise: 0.018, impact: 0 }
    const samples = new Array<number>(N)
    let sumSq = 0
    for (let i = 0; i < N; i++) {
      let v =
        amps.a1 * Math.sin((2 * Math.PI * f1 * i) / fs + ph1) +
        amps.a2 * Math.sin((2 * Math.PI * f2 * i) / fs + ph2) +
        amps.a3 * Math.sin((2 * Math.PI * 0.6 * i) / fs + ph3) +
        (rand() - 0.5) * 2 * amps.noise
      if (rupture && i % 25 === 0) v += (rand() - 0.5) * 2 * amps.impact
      samples[i] = v
      sumSq += v * v
    }
    const rms = Math.sqrt(sumSq / N)
    const flag = rupture && rand() < 0.45 ? 1 : 0
    const spec = spectrumMagnitudes(samples, 512, 256)
    // D2-9 staleness: offline replay streams all three nodes every second
    s.setNodeSeen(6, Date.now())
    s.setNodeSeen(7, Date.now())
    s.setNodeSeen(8, Date.now())
    s.setSpectrum(spec)
    s.setLive({ rms: Math.round(rms * 1000) / 1000, freq: f1, flag })
  }

  const emitBhi = () => {
    const s = useStore.getState()
    const rupture = s.scenario === 'rupture'
    if (rupture) {
      if (prevScenario !== 'rupture') damageClock = 0
      damageClock += 1
    } else {
      damageClock = Math.max(0, damageClock - 1.5)
    }
    prevScenario = s.scenario

    const e = smooth(clamp(damageClock / 28, 0, 1))
    const noise = (rand() - 0.5) * 0.02
    const cv = clamp(0.12 + (0.5 - 0.12) * e + noise, 0, 1)
    const vib = clamp(0.14 + (0.55 - 0.14) * e + noise, 0, 1)
    const load = clamp(0.3 + (0.48 - 0.3) * e + noise * 0.5, 0, 1)
    const bhi = computeBhi(cv, vib, load)
    const u = Math.round((1.5 + 6 * e + rand() * 0.5) * 100) / 100
    useStore.getState().setLive({ bhi, u, cv, vib, load, state: stateFor(bhi) })

    // Keep the box-girder physics overlay honest offline: f1 drops with the
    // damage clock, EI drift + inferred damage follow (mirrors the live overlay).
    const f1 = rupture ? 3.8 - 0.28 * e : 3.8
    useStore.getState().setStiffness({
      f1Meas: Math.round(f1 * 100) / 100,
      f1Ref: 3.8,
      eiDriftPct: Math.round((1 - (f1 / 3.8) ** 2) * 1000) / 10,
      damagePct: Math.round(31 * e * 10) / 10,
      freqs: [Math.round(f1 * 100) / 100, 10.2],
      baselineLocked: true,
      stale: false,
    })

    // Scripted alert sequence during the rupture story arc.
    if (rupture && damageClock === 1) {
      pushAlert(
        'critical',
        'fusion',
        'Stiffness-loss signature detected (multi-modal evidence)',
        'Impose load restriction to 20 t and dispatch strain-gauge verification to node 7.',
      )
    } else if (rupture && damageClock === 8) {
      pushAlert(
        'warning',
        'vib',
        'Vertical acceleration RMS exceeded 0.25 m/s² threshold',
        'Switch span to active monitoring cadence (1 Hz -> 10 Hz).',
      )
    } else if (rupture && damageClock === 16) {
      pushAlert(
        'critical',
        'cv',
        'Mid-span deflection growth observed — confirm with LVDT/optical survey',
        'Restrict heavy traffic and schedule visual inspection within 48 h.',
      )
    } else if (rupture && damageClock === 26) {
      pushAlert(
        'warning',
        'load',
        'Traffic loading redistribution measured across nodes 6-8',
        'Re-run weigh-in-motion calibration after structural verification.',
      )
    } else if (s.scenario === 'healthy' && tick % 22 === 0) {
      pushAlert('info', 'cv', 'All channels nominal — no anomaly in the last 10.24 s window')
    }
    tick += 1
  }

  emitAccel()
  emitBhi()
  const accelTimer = window.setInterval(emitAccel, 1000)
  const bhiTimer = window.setInterval(emitBhi, 1000)
  timers = [accelTimer, bhiTimer]
  return stopReplay
}

export function stopReplay(): void {
  for (const t of timers) window.clearInterval(t)
  timers = []
}
