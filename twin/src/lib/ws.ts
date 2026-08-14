// WebSocket client for the digital twin.
//
// Connects to the backend WS bridge (ws://localhost:8765) using the browser
// native WebSocket. Messages are parsed by payload shape into the store,
// mirroring the contract topics: bridge/z24/accel, /bhi, /alert, /frame.
//
// HONESTY RULE: if the bridge cannot be reached (connect failure, error, or a
// 3 s timeout) we switch to REPLAY MODE and label every source "REPLAY". The
// demo therefore runs fully offline, and every UI source is labeled.
// Robustness: we keep retrying the live connection every few seconds so the
// twin flips from REPLAY to LIVE automatically once the backend is up — the
// presenter can start the backend and open the twin in any order.
import { useStore, computeBhi, stateFor } from '../store'
import type { AlertSource, Severity } from '../store'
import { spectrumMagnitudes } from './fft'
import { startReplay, stopReplay } from './fixtures'

// 127.0.0.1 (not "localhost") — the backend WS bridge binds IPv4 0.0.0.0, and
// browsers resolve "localhost" to ::1 first, so the handshake stalls and the
// 3 s fallback timer fires. Explicit IPv4 avoids the dual-stack race.
const WS_URL = 'ws://127.0.0.1:8765'
const FALLBACK_TIMEOUT_MS = 3000
const RETRY_DELAY_MS = 5000

interface FrameDetection {
  cls?: string
  conf?: number
}

function rmsOf(samples: number[]): number {
  let sum = 0
  for (const v of samples) sum += v * v
  return Math.sqrt(sum / Math.max(1, samples.length))
}

function toAlertSource(s: string): AlertSource {
  return s === 'cv' || s === 'vib' || s === 'load' || s === 'fusion' ? s : 'fusion'
}

function toSeverity(s: string): Severity {
  return s === 'info' || s === 'warning' || s === 'critical' ? s : 'info'
}

function ingest(payload: unknown): void {
  const s = useStore.getState()
  if (!payload || typeof payload !== 'object') return
  const p = payload as Record<string, unknown>

  // --- control/cmd scenario: { cmd: "scenario", scenario: healthy|rupture }
  // The storyboard driver publishes this once (t=75) and the ws bridge replays
  // the current value to freshly-connected clients, so the LIVE path drives the
  // same scenario the replay fixtures drive offline — labels, sensor colors and
  // the collapse animation all follow the arc instead of staying "healthy".
  if (p.cmd === 'scenario' && (p.scenario === 'healthy' || p.scenario === 'rupture')) {
    s.setScenario(p.scenario)
    return
  }

  // --- accel (bridge/z24/accel): { bridge, node, ts, fs, samples[], rms, flag }
  if (Array.isArray(p.samples)) {
    const samples = (p.samples as number[]).map(Number)
    const rms = typeof p.rms === 'number' ? p.rms : rmsOf(samples)
    const flag = typeof p.flag === 'number' ? p.flag : 0
    if (typeof p.node === 'number') s.setNodeSeen(p.node, Date.now()) // D2-9 staleness
    s.setSpectrum(spectrumMagnitudes(samples, 512, 256))
    s.setLive({ rms: Math.round(rms * 1000) / 1000, flag })
    return
  }

  // --- bhi (bridge/z24/bhi): { bridge, ts, bhi, u, cv, vib, load, state }
  if (typeof p.bhi === 'number') {
    const cv = typeof p.cv === 'number' ? p.cv : s.live.cv
    const vib = typeof p.vib === 'number' ? p.vib : s.live.vib
    const load = typeof p.load === 'number' ? p.load : s.live.load
    const bhi = typeof p.bhi === 'number' ? (p.bhi as number) : computeBhi(cv, vib, load)
    const state = typeof p.state === 'string' ? (p.state as 'GREEN' | 'AMBER' | 'RED') : stateFor(bhi)
    const u = typeof p.u === 'number' ? (p.u as number) : s.live.u
    s.setLive({ bhi, u, cv, vib, load, state })
    return
  }

  // --- alert (bridge/z24/alert): { bridge, ts, severity, source, text, recommendation }
  if (typeof p.text === 'string' || typeof p.severity === 'string') {
    s.pushAlert({
      severity: toSeverity(typeof p.severity === 'string' ? p.severity : 'info'),
      source: toAlertSource(typeof p.source === 'string' ? p.source : 'fusion'),
      text: typeof p.text === 'string' ? p.text : 'Unknown event',
      recommendation: typeof p.recommendation === 'string' ? p.recommendation : undefined,
    })
    return
  }

  // --- frame (bridge/z24/frame): { bridge, ts, cam, image_b64, detections[] }
  if (typeof p.image_b64 === 'string') {
    const dets = Array.isArray(p.detections) ? (p.detections as FrameDetection[]) : []
    if (dets.length > 0) {
      s.pushAlert({
        severity: 'warning',
        source: 'cv',
        text: `${dets.length} visual defect(s) detected in frame`,
        recommendation: 'Review camera frame and schedule inspection',
      })
    }
  }
}

let ws: WebSocket | null = null
let retryTimer: ReturnType<typeof setTimeout> | null = null
let live = false

function clearRetry(): void {
  if (retryTimer !== null) {
    clearTimeout(retryTimer)
    retryTimer = null
  }
}

function scheduleRetry(): void {
  if (retryTimer !== null) return
  retryTimer = setTimeout(() => {
    retryTimer = null
    attempt()
  }, RETRY_DELAY_MS)
}

function ensureReplay(): void {
  // startReplay() is idempotent (stops prior timers first) and sets wsStatus.
  startReplay()
}

function attempt(): void {
  clearRetry()
  try {
    ws?.close()
  } catch {
    /* noop */
  }
  ws = null

  let timedOut = false
  const sock = new WebSocket(WS_URL)
  ws = sock

  const timeout = setTimeout(() => {
    timedOut = true
    if (!live) {
      ensureReplay()
      scheduleRetry()
    }
    try {
      sock.close()
    } catch {
      /* noop */
    }
  }, FALLBACK_TIMEOUT_MS)

  sock.onopen = () => {
    if (ws !== sock) return
    clearTimeout(timeout)
    if (!live) {
      live = true
      stopReplay()
      useStore.getState().setWsStatus('live')
    }
  }

  sock.onmessage = (ev) => {
    try {
      const data = JSON.parse(String(ev.data))
      const p = data && typeof data === 'object' ? (data as Record<string, unknown>) : {}
      // Accept both raw payloads and a { topic, payload } envelope.
      if (p && 'payload' in p && p.payload && typeof p.payload === 'object') {
        ingest(p.payload)
      } else {
        ingest(data)
      }
    } catch {
      // malformed frame — ignore
    }
  }

  sock.onerror = () => {
    clearTimeout(timeout)
    if (!live) {
      ensureReplay()
      scheduleRetry()
    }
    try {
      sock.close()
    } catch {
      /* noop */
    }
  }

  sock.onclose = () => {
    clearTimeout(timeout)
    if (ws === sock) ws = null
    if (live) {
      // dropped a live connection — go back to honest REPLAY and keep trying
      live = false
      ensureReplay()
      scheduleRetry()
    } else if (retryTimer === null) {
      ensureReplay()
      scheduleRetry()
    }
  }
}

export function connect(): void {
  attempt()
}
