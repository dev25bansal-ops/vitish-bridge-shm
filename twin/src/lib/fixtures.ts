// Deterministic offline fixture generator — powers REPLAY mode when the live
// WebSocket bridge is unreachable. Same payload shapes as the contract
// (bridge/z24/accel, /bhi, /alert), so the whole demo runs with NO network.
import { useStore, computeBhi, stateFor, F1_REF_HZ, WINDOW_S } from '../store'
import type { AlertSource, Bridge, Severity } from '../store'
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

/** Z24 seeded-defect FEM trajectory (mirrors models/vibration/seeded_defect.py
 * + models/vibration/stiffness.snapshot).  alpha -> [f1 Hz, seeded main-span EI
 * loss %, model-inferred damage %].  Computed from the real continuous 3-span
 * FEM with the Z24 campaign defects folded in (settlement reaches full severity
 * at alpha ~0.33, cracking ~0.67, tendon rupture ~1.0).  The offline fixture
 * samples this piecewise-linearly so its f1 / EI / damage numbers MATCH the
 * live overlay instead of drifting to a different damage state. */
const Z24_FEM: ReadonlyArray<readonly [number, number, number, number]> = [
  [0.0, F1_REF_HZ, 0.0, 0.0],
  [0.33, 3.778, 3.4, 0.0],
  [0.5, 3.694, 7.4, 12.4],
  [0.67, 3.608, 11.1, 21.7],
  [0.85, 3.417, 17.7, 39.9],
  [1.0, 3.244, 22.6, 53.9],
]

function femAt(e: number): { f1: number; eiLoss: number; damage: number } {
  const x = clamp(e, 0, 1)
  for (let i = 1; i < Z24_FEM.length; i++) {
    const [a0, f0, s0, d0] = Z24_FEM[i - 1]
    const [a1, f1, s1, d1] = Z24_FEM[i]
    if (x <= a1) {
      const t = (x - a0) / (a1 - a0)
      return {
        f1: f0 + (f1 - f0) * t,
        eiLoss: s0 + (s1 - s0) * t,
        damage: d0 + (d1 - d0) * t,
      }
    }
  }
  const [f, s, d] = Z24_FEM[Z24_FEM.length - 1]
  return { f1: f, eiLoss: s, damage: d }
}

/** D2-12 offline mirror of the seeded-defect narrative (replay fixture).
 * The fixture samples the SAME FEM trajectory the live backend evaluates
 * (settlement -> cracking -> tendon rupture), so offline f1 / EI match the
 * live overlay: full rupture reads f1 3.80 -> 3.24 Hz, main-span EI -22.6%. */
function seededFixtureState(e: number) {
  const { f1, eiLoss } = femAt(e)
  const label =
    e < 1e-6 ? 'none'
      : e < 0.34 ? 'pier settlement -> cracks'
        : e < 0.67 ? 'mid-span concrete cracking'
          : 'tendon rupture'
  const mainLoss = Math.round(eiLoss * 10) / 10
  return {
    active: [],
    label,
    source: e < 1e-6 ? '' : 'Z24 benchmark',
    f1: Math.round(f1 * 100) / 100,
    f1Ref: F1_REF_HZ,
    f1DriftPct: Math.round((f1 / F1_REF_HZ - 1) * 10000) / 100,
    eiLoss: mainLoss,
    perSpanLossPct: [0, mainLoss, 0] as [number, number, number],
    note: 'offline replay fixture mirrors the live Z24 seeded-defect overlay',
  }
}

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
    name: 'Z24 · Box Girder (Nottwil, CH — A1)',
    lat: 47.135,
    lng: 8.165,
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
  // Damage envelope 0..1 shared by the accel waveform and the overlay, so the
  // offline "measured" f1 and the seeded-defect f1 slide in lockstep.
  const envelope = () => smooth(clamp(damageClock / 28, 0, 1))

  const pushAlert = (severity: Severity, source: AlertSource, text: string, recommendation?: string) => {
    useStore.getState().pushAlert({ severity, source, text, recommendation })
  }

  const emitAccel = () => {
    const s = useStore.getState()
    const rupture = s.scenario === 'rupture'
    const ph1 = rand() * Math.PI * 2
    const ph2 = rand() * Math.PI * 2
    const ph3 = rand() * Math.PI * 2
    // Z24 box-girder modes: healthy f1 = 3.8 Hz (f2 = 15.2); rupture slides f1
    // along the seeded-defect FEM trajectory (full tendon rupture = 3.24 Hz,
    // matching the live overlay) and adds broadband impact energy.
    const f1 = rupture ? femAt(envelope()).f1 : F1_REF_HZ
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

    const e = envelope()
    const noise = (rand() - 0.5) * 0.02
    const cv = clamp(0.12 + (0.5 - 0.12) * e + noise, 0, 1)
    const vib = clamp(0.14 + (0.55 - 0.14) * e + noise, 0, 1)
    const load = clamp(0.3 + (0.48 - 0.3) * e + noise * 0.5, 0, 1)
    const bhi = computeBhi(cv, vib, load)
    const u = Math.round((1.5 + 6 * e + rand() * 0.5) * 100) / 100
    useStore.getState().setLive({ bhi, u, cv, vib, load, state: stateFor(bhi) })

    // Keep the box-girder physics overlay honest offline: f1 slides along the
    // SAME seeded-defect FEM trajectory the live backend evaluates, so the
    // offline "measured" f1 matches the live overlay at every damage stage.
    const f1 = rupture ? femAt(e).f1 : F1_REF_HZ
    useStore.getState().setStiffness({
      f1Meas: Math.round(f1 * 100) / 100,
      f1Ref: F1_REF_HZ,
      eiDriftPct: Math.round((1 - (f1 / F1_REF_HZ) ** 2) * 1000) / 10,
      damagePct: Math.round(femAt(e).damage * 10) / 10,
      freqs: [Math.round(f1 * 100) / 100, 10.2],
      baselineLocked: true,
      stale: false,
    })
    // D2-12 seeded-defect narrative, offline mirror (label, EI loss, f1 slide).
    useStore.getState().setSeededDefect(seededFixtureState(e))

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
      pushAlert('info', 'cv', `All channels nominal — no anomaly in the last ${WINDOW_S} s window`)
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
