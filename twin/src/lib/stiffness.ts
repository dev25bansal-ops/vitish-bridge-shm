// Stiffness overlay poller — pulls the Z24 box-girder physics snapshot from
// the backend REST API (GET /api/bridge/z24/stiffness) and merges it into the
// store.  The twin is WS-driven for telemetry (BHI/accel/alerts); the physics
// overlay (measured f1, EI drift, model-inferred damage %, FEM mode shapes) is
// a slower-changing explainability layer, so a light poll is honest and simple.
//
// Falls back to the analytic reference silently: if the backend is down, the
// store keeps its default (f1 3.8 Hz, no drift) and the mode animation falls
// back to the reference simple-span sine (scene/collapse.ts).
import { useStore } from '../store'

const STIFFNESS_URL = 'http://127.0.0.1:8000/api/bridge/z24/stiffness'
const POLL_MS = 1500

let timer: ReturnType<typeof setInterval> | null = null

async function poll(): Promise<void> {
  try {
    const res = await fetch(STIFFNESS_URL)
    if (!res.ok) return
    const s = (await res.json()) as Record<string, unknown>
    if (typeof s.f1_meas !== 'number') return
    const st = useStore.getState()
    st.setStiffness({
      f1Meas: s.f1_meas as number,
      f1Ref: (s.f1_ref as number) ?? 3.8,
      eiDriftPct: (s.ei_drift_pct as number) ?? 0,
      damagePct: (s.damage_pct as number) ?? 0,
      freqs: Array.isArray(s.freqs) ? (s.freqs as number[]) : [3.8],
      x: Array.isArray(s.x) ? (s.x as number[]) : [],
      shapes: Array.isArray(s.shapes) ? (s.shapes as number[][]) : [],
      baselineLocked: s.baseline_locked === true,
      stale: s.stale === true,
      // D2-10 thermal overlay fields (simulated seasonal model, see models/vibration/temperature.py)
      simDay: typeof s.sim_day === 'number' ? (s.sim_day as number) : undefined,
      simClock: typeof s.sim_clock === 'string' ? (s.sim_clock as string) : undefined,
      tempC: typeof s.temp_c === 'number' ? (s.temp_c as number) : undefined,
      tempSource: typeof s.temp_source === 'string' ? (s.temp_source as string) : undefined,
      f1ExpectedThermal: typeof s.f1_expected_thermal === 'number'
        ? (s.f1_expected_thermal as number)
        : undefined,
      thermalShiftPct: typeof s.thermal_shift_pct === 'number'
        ? (s.thermal_shift_pct as number)
        : undefined,
      residualDriftPct: typeof s.residual_drift_pct === 'number'
        ? (s.residual_drift_pct as number)
        : undefined,
      residualBandPct: typeof s.residual_band_pct === 'number'
        ? (s.residual_band_pct as number)
        : undefined,
      residualInterpretation: typeof s.residual_interpretation === 'string'
        ? (s.residual_interpretation as string)
        : undefined,
    })
    // Keep the popup's live.freq honest when the overlay is authoritative.
    st.setLive({ freq: s.f1_meas as number })
  } catch {
    // backend unreachable — replay/reference fallback stays in effect
  }
}

export function startStiffnessPolling(): void {
  if (timer !== null) return
  poll()
  timer = setInterval(poll, POLL_MS)
}

export function stopStiffnessPolling(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}
