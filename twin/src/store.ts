import { create } from 'zustand'

// ---------------------------------------------------------------------------
// Shared types — mirror the authoritative contract (backend/app/contract.py).
// BHI = 100 * (1 - 0.40*cv - 0.35*vib - 0.25*load); GREEN>=70, AMBER [50,70), RED<50.
// Inference window: 10.24 s @ 100 Hz = 1024 samples.
// ---------------------------------------------------------------------------

export type HealthState = 'GREEN' | 'AMBER' | 'RED'
export type Severity = 'info' | 'warning' | 'critical'
export type WsStatus = 'connecting' | 'live' | 'replay'
export type Scenario = 'healthy' | 'rupture'
export type AlertSource = 'cv' | 'vib' | 'load' | 'fusion'

export interface Bridge {
  id: string
  name: string
  lat: number
  lng: number
  bhi: number
  state: HealthState
}

export interface Sensor {
  id: number
  node: number
  x: number
  y: number
  z: number
}

export interface LiveState {
  bhi: number
  u: number
  cv: number
  vib: number
  load: number
  state: HealthState
  rms: number
  freq: number
  flag: number
  /** ROADMAP line 68: floor vs trained-push split of the last scored window. */
  vibEvidence?: { floor: number; trained_push: number; score: number }
}

/** Z24 box-girder physics overlay (see backend/app/stiffness.py). */
export interface StiffnessState {
  f1Meas: number // measured first vertical mode (Hz)
  f1Ref: number // healthy baseline f1 (Hz)
  eiDriftPct: number // stiffness drift vs baseline (%)
  damagePct: number // model-inferred mid-span stiffness loss (%)
  freqs: number[] // FEM mode frequencies (Hz)
  x: number[] // FEM deck sample coordinates (m, 0..58)
  shapes: number[][] // FEM mode shapes, one array of deck deflections per mode
  baselineLocked: boolean
  stale: boolean
  // D2-10 temperature-compensated overlay (simulated seasonal model)
  simDay?: number
  simClock?: string
  tempC?: number
  tempSource?: string
  f1ExpectedThermal?: number
  thermalShiftPct?: number
  residualDriftPct?: number
  residualBandPct?: number
  residualInterpretation?: string
}

/** One channel's honest provenance (see backend/app/channel_models.py). */
export interface ChannelProvenance {
  node: number
  source: string // 'z24-replay' | 'synthetic' | 'live-demo'
  real: boolean
  sensor: string
}

/** D1-5/D1-6 data-realism manifest — what am I actually looking at? */
export interface ManifestState {
  dataSource: 'z24-replay' | 'synthetic' | 'live-demo' | 'offline'
  dataSourceLabel: string
  channels: ChannelProvenance[]
  honestyNote: string
  liveFeedActive: boolean
  liveFeedBridge: string
}

export interface Alert {
  id: number
  ts: number
  severity: Severity
  source: AlertSource
  text: string
  recommendation?: string
}

/** One active seeded defect (D2-12, see models/vibration/seeded_defect.py). */
export interface SeededDefect {
  key: string
  short: string
  source: string
  progress: number // 0..1 severity staged in
  eiLossPct: number // this defect's EI reduction at current progress (%)
  zone: [number, number] // x-range (m) over which EI is reduced
}

/**
 * D2-12 seeded-defect narrative — what the demo scenario actually injected.
 * The EI loss is the MODEL's seeded ground truth, never a claim about the real
 * bridge (see models/vibration/seeded_defect.py `describe`).
 */
export interface SeededDefectState {
  active: SeededDefect[]
  label: string // dominant defect short label, or 'none'
  source: string // 'Z24 benchmark' | 'S101 benchmark'
  f1: number // FEM first mode under the current defect set (Hz)
  f1Ref: number // healthy baseline f1 (Hz)
  f1DriftPct: number // % f1 drift vs baseline
  eiLossPct: number // worst-span seeded EI loss (%)
  perSpanLossPct: [number, number, number] // left / main / right span
  note: string
}

/** D2-11 Markov projection row (see backend/app/deterioration.py). */
export interface DeteriorationRow {
  year: number
  expected: number
  p10: number
  p90: number
  p_poor: number
  dist: number[]
}

/** D2-11 deterioration payload from GET /api/bridge/z24/deterioration. */
export interface DeteriorationState {
  currentBhi: number
  currentCondition: number
  priorsLabel: string
  note: string
  nextInspectionYear: number | null
  nextInspectionRule: string
  projection: DeteriorationRow[]
  rating: string
}

export interface TwinState {
  bridges: Bridge[]
  sensors: Sensor[]
  selectedBridgeId: string
  selectedSensorId: number | null
  live: LiveState
  stiffness: StiffnessState
  seededDefect: SeededDefectState
  manifest: ManifestState
  deterioration: DeteriorationState
  spectrum: number[]
  bhiTrend: number[]
  alerts: Alert[]
  wsStatus: WsStatus
  scenario: Scenario
  collapseEpoch: number
  /** D2-9 per-node last-seen (ms epoch) for stale-sensor glyphs. */
  nodeSeen: Record<number, number>
  setSelectedBridgeId: (id: string) => void
  setSelectedSensorId: (id: number | null) => void
  setBridges: (bridges: Bridge[]) => void
  setLive: (patch: Partial<LiveState>) => void
  setStiffness: (s: Partial<StiffnessState>) => void
  setSeededDefect: (s: Partial<SeededDefectState>) => void
  setManifest: (m: Partial<ManifestState>) => void
  setDeterioration: (d: Partial<DeteriorationState>) => void
  setSpectrum: (s: number[]) => void
  pushAlert: (a: Omit<Alert, 'id' | 'ts'>) => void
  setWsStatus: (s: WsStatus) => void
  setScenario: (s: Scenario) => void
  setCollapseEpoch: (n: number) => void
  replayCollapse: () => void
  setNodeSeen: (node: number, ms: number) => void
}

// --- contract constants (kept in sync with backend/app/contract.py) ---------
export const BHI_GREEN = 70.0
export const BHI_AMBER = 50.0
export const BHI_W = { cv: 0.4, vib: 0.35, load: 0.25 }
export const AGE_FACTOR = 1.0 // demo: 1.0 (age model added on pilot data)
export const TRAFFIC_FACTOR = 1.0 // demo: 1.0
export const WINDOW_N = 1024
export const FS_HZ = 100
export const WINDOW_S = WINDOW_N / FS_HZ // 10.24 s
export const WINDOW_LABEL = `window ${WINDOW_S} s · fs ${FS_HZ} Hz`
export const F1_REF_HZ = 3.8 // Z24 healthy first-bending reference (f2 = 15.2)
export const BRIDGE_DECK_Y = 6 // Z24 box-girder deck soffit height (m)

export function stateFor(bhi: number): HealthState {
  if (bhi >= BHI_GREEN) return 'GREEN'
  if (bhi >= BHI_AMBER) return 'AMBER'
  return 'RED'
}

// Mirrors backend contract.compute_bhi(cv, vib, load, w, age_factor, traffic_factor)
// exactly for the default weights — same weighted penalty, same age/traffic
// multipliers (default 1.0 in the demo), same round-to-0.1.  NOTE: the backend's
// 4th positional param is a weights override `w`; this twin keeps the weights
// fixed as BHI_W and puts ageFactor in the 4th slot, so positional args beyond
// the third do NOT line up with the Python signature.  Only the 3-arg form is
// used in the demo path (fixtures.ts / ws.ts both call 3-arg), so the parity
// that matters is exact; a caller wanting custom weights must change both sides.
// ageFactor/trafficFactor default to the shared constants so callers get the
// honest contract value unless they opt in.
export function computeBhi(
  cv: number,
  vib: number,
  load: number,
  ageFactor = AGE_FACTOR,
  trafficFactor = TRAFFIC_FACTOR,
): number {
  const c = Math.min(1, Math.max(0, cv))
  const v = Math.min(1, Math.max(0, vib))
  const l = Math.min(1, Math.max(0, load))
  const penalty = BHI_W.cv * c + BHI_W.vib * v + BHI_W.load * l
  const bhi = 100 * (1 - penalty) * ageFactor * trafficFactor
  return Math.round(Math.min(100, Math.max(0, bhi)) * 10) / 10
}

const TREND_MAX = 120
const ALERTS_MAX = 40
let alertSeq = 0

const STIFFNESS_EMPTY: StiffnessState = {
  f1Meas: F1_REF_HZ,
  f1Ref: F1_REF_HZ,
  eiDriftPct: 0,
  damagePct: 0,
  freqs: [F1_REF_HZ],
  x: [],
  shapes: [],
  baselineLocked: false,
  stale: true,
}

/** Honest "no narrative yet" default until the backend reports the seeded set. */
const SEEDED_DEFECT_EMPTY: SeededDefectState = {
  active: [],
  label: 'none',
  source: '',
  f1: F1_REF_HZ,
  f1Ref: F1_REF_HZ,
  f1DriftPct: 0,
  eiLossPct: 0,
  perSpanLossPct: [0, 0, 0],
  note: 'seeded-defect narrative not available (backend unreachable)',
}

/** Honest offline default until the manifest poller reports back. */
const MANIFEST_OFFLINE: ManifestState = {
  dataSource: 'offline',
  dataSourceLabel: 'replay fixtures (backend unreachable)',
  channels: [],
  honestyNote: 'Waiting for the data-realism manifest (backend /api/manifest).',
  liveFeedActive: false,
  liveFeedBridge: '',
}

/** Honest "no data yet" default — the panel shows the offline label. */
const DETERIORATION_EMPTY: DeteriorationState = {
  currentBhi: 87,
  currentCondition: 8,
  priorsLabel: 'Markov projection not available (backend unreachable)',
  note: '',
  nextInspectionYear: null,
  nextInspectionRule: '',
  projection: [],
  rating: 'super',
}

export const useStore = create<TwinState>((set, get) => ({
  bridges: [],
  sensors: [
    // Z24 accelerometer nodes on the box-girder deck (main span, x = -10/0/+10).
    { id: 0, node: 6, x: -10, y: BRIDGE_DECK_Y, z: 2.3 },
    { id: 1, node: 7, x: 0, y: BRIDGE_DECK_Y, z: 2.3 },
    { id: 2, node: 8, x: 10, y: BRIDGE_DECK_Y, z: 2.3 },
  ],
  selectedBridgeId: 'z24',
  selectedSensorId: null,
  live: { bhi: 82.0, u: 1.8, cv: 0.12, vib: 0.14, load: 0.3, state: 'GREEN', rms: 0.08, freq: F1_REF_HZ, flag: 0, vibEvidence: { floor: 0.14, trained_push: 0, score: 0.14 } },
  stiffness: STIFFNESS_EMPTY,
  seededDefect: SEEDED_DEFECT_EMPTY,
  manifest: MANIFEST_OFFLINE,
  deterioration: DETERIORATION_EMPTY,
  spectrum: [],
  bhiTrend: [],
  alerts: [],
  wsStatus: 'connecting',
  scenario: 'healthy',
  collapseEpoch: 0,
  nodeSeen: {},

  setSelectedBridgeId: (id) => set({ selectedBridgeId: id }),
  setSelectedSensorId: (id) => set({ selectedSensorId: id }),

  setBridges: (bridges) => set({ bridges }),

  setLive: (patch) => {
    const live = { ...get().live, ...patch }
    if (patch.bhi !== undefined) {
      live.state = patch.state ?? stateFor(patch.bhi)
      let trend = get().bhiTrend
      trend = [...trend, patch.bhi]
      if (trend.length > TREND_MAX) trend = trend.slice(trend.length - TREND_MAX)
      set({ live, bhiTrend: trend })
    } else {
      set({ live })
    }
  },

  setStiffness: (patch) => set({ stiffness: { ...get().stiffness, ...patch } }),

  setSeededDefect: (patch) =>
    set({ seededDefect: { ...get().seededDefect, ...patch } }),

  setManifest: (patch) => set({ manifest: { ...get().manifest, ...patch } }),

  setDeterioration: (patch) =>
    set({ deterioration: { ...get().deterioration, ...patch } }),

  setSpectrum: (spectrum) => set({ spectrum }),

  pushAlert: (a) => {
    const alert: Alert = { ...a, id: ++alertSeq, ts: Date.now() }
    set({ alerts: [alert, ...get().alerts].slice(0, ALERTS_MAX) })
  },

  setWsStatus: (wsStatus) => set({ wsStatus }),
  setScenario: (scenario) => set({ scenario }),
  setCollapseEpoch: (collapseEpoch) => set({ collapseEpoch }),
  replayCollapse: () => set((st) => ({ scenario: 'rupture', collapseEpoch: st.collapseEpoch + 1 })),
  setNodeSeen: (node, ms) =>
    set((st) => ({ nodeSeen: st.nodeSeen[node] === ms ? st.nodeSeen : { ...st.nodeSeen, [node]: ms } })),
}))
