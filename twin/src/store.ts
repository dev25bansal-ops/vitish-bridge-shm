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
}

export interface Alert {
  id: number
  ts: number
  severity: Severity
  source: AlertSource
  text: string
  recommendation?: string
}

export interface TwinState {
  bridges: Bridge[]
  sensors: Sensor[]
  selectedBridgeId: string
  selectedSensorId: number | null
  live: LiveState
  spectrum: number[]
  bhiTrend: number[]
  alerts: Alert[]
  wsStatus: WsStatus
  scenario: Scenario
  collapseEpoch: number
  setSelectedBridgeId: (id: string) => void
  setSelectedSensorId: (id: number | null) => void
  setLive: (patch: Partial<LiveState>) => void
  setSpectrum: (s: number[]) => void
  pushAlert: (a: Omit<Alert, 'id' | 'ts'>) => void
  setWsStatus: (s: WsStatus) => void
  setScenario: (s: Scenario) => void
  setCollapseEpoch: (n: number) => void
  replayCollapse: () => void
}

// --- contract constants (kept in sync with backend/app/contract.py) ---------
export const BHI_GREEN = 70.0
export const BHI_AMBER = 50.0
export const BHI_W = { cv: 0.4, vib: 0.35, load: 0.25 }
export const WINDOW_N = 1024

export function stateFor(bhi: number): HealthState {
  if (bhi >= BHI_GREEN) return 'GREEN'
  if (bhi >= BHI_AMBER) return 'AMBER'
  return 'RED'
}

export function computeBhi(cv: number, vib: number, load: number): number {
  const c = Math.min(1, Math.max(0, cv))
  const v = Math.min(1, Math.max(0, vib))
  const l = Math.min(1, Math.max(0, load))
  const penalty = BHI_W.cv * c + BHI_W.vib * v + BHI_W.load * l
  const bhi = 100 * (1 - penalty)
  return Math.round(Math.min(100, Math.max(0, bhi)) * 10) / 10
}

const TREND_MAX = 120
const ALERTS_MAX = 40
let alertSeq = 0

export const useStore = create<TwinState>((set, get) => ({
  bridges: [],
  sensors: [
    { id: 0, node: 6, x: -46, y: 15.6, z: 4.6 },
    { id: 1, node: 7, x: 0, y: 15.6, z: 4.6 },
    { id: 2, node: 8, x: 46, y: 15.6, z: 4.6 },
  ],
  selectedBridgeId: 'z24',
  selectedSensorId: null,
  live: { bhi: 82.0, u: 1.8, cv: 0.12, vib: 0.14, load: 0.3, state: 'GREEN', rms: 0.08, freq: 5.2, flag: 0 },
  spectrum: [],
  bhiTrend: [],
  alerts: [],
  wsStatus: 'connecting',
  scenario: 'healthy',
  collapseEpoch: 0,

  setSelectedBridgeId: (id) => set({ selectedBridgeId: id }),
  setSelectedSensorId: (id) => set({ selectedSensorId: id }),

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

  setSpectrum: (spectrum) => set({ spectrum }),

  pushAlert: (a) => {
    const alert: Alert = { ...a, id: ++alertSeq, ts: Date.now() }
    set({ alerts: [alert, ...get().alerts].slice(0, ALERTS_MAX) })
  },

  setWsStatus: (wsStatus) => set({ wsStatus }),
  setScenario: (scenario) => set({ scenario }),
  setCollapseEpoch: (collapseEpoch) => set({ collapseEpoch }),
  replayCollapse: () => set((st) => ({ scenario: 'rupture', collapseEpoch: st.collapseEpoch + 1 })),
}))
