// Mutable collapse state + pure bridge geometry functions shared by the
// parametric bridge, the sensor markers and the popup. Everything is derived
// from a single animation clock advanced once per frame in MorbiBridge.
import type { Scenario } from '../store'

export interface CollapseState {
  cableBroken: boolean
  cableDrop: number // 0..1 snap of the broken cable (fast)
  sag: number // 0..1 deck droop (slow)
  cascade: number // 0..1 sensor cascade vibration (slowest)
}

export const collapseState: CollapseState = {
  cableBroken: false,
  cableDrop: 0,
  sag: 0,
  cascade: 0,
}

export const BRIDGE = {
  L: 230,
  half: 115,
  towerX: 100,
  towerTop: 40,
  deckY: 14,
  midSag: 22,
  anchorX: 112,
  zCable: 4.5,
  zDeck: 4.6,
}

const T_ANIM_MAX = 15 // 15 s story arc
let animT = 0

const clamp01 = (v: number) => Math.max(0, Math.min(1, v))
const smooth = (x: number) => x * x * (3 - 2 * x)

function gauss(x: number, cx: number, sigma: number): number {
  return Math.exp(-((x - cx) ** 2) / (2 * sigma * sigma))
}

function sync(): void {
  const t = Math.max(0, Math.min(T_ANIM_MAX, animT))
  collapseState.cableBroken = t > 2.5
  collapseState.cableDrop = smooth(clamp01((t - 2.5) / 1.8))
  collapseState.sag = smooth(clamp01((t - 3.5) / 6.5))
  collapseState.cascade = smooth(clamp01((t - 7) / 8))
}

export function resetCollapse(): void {
  animT = 0
  sync()
}

/** Advance the story-arc clock. Call once per frame from MorbiBridge. */
export function tickCollapse(scenario: Scenario, delta: number): void {
  const target = scenario === 'rupture' ? T_ANIM_MAX : 0
  const speed = scenario === 'rupture' ? 1 : 3 // recovery animates 3x faster
  const diff = target - animT
  const step = Math.sign(diff) * Math.min(Math.abs(diff), delta * speed)
  animT += step
  sync()
}

// --- geometry (pure; driven by the mutable collapseState) ------------------

/** Deck surface height at span coordinate x (m). */
export function deckYAt(x: number): number {
  const pDeck = Math.max(0, 1 - (x / BRIDGE.towerX) ** 2)
  const g = gauss(x, -18, 60)
  return BRIDGE.deckY - collapseState.sag * 6 * pDeck - collapseState.sag * 5 * g
}

/** Main-cable height at span coordinate x (m). */
export function cableYAt(x: number): number {
  const abs = Math.abs(x)
  if (abs >= BRIDGE.towerX) {
    const t = clamp01((abs - BRIDGE.towerX) / (BRIDGE.anchorX - BRIDGE.towerX))
    return BRIDGE.towerTop + (BRIDGE.deckY - BRIDGE.towerTop) * t
  }
  const p = 1 - (x / BRIDGE.towerX) ** 2
  const g = gauss(x, -18, 60)
  return BRIDGE.towerTop - BRIDGE.midSag * p - 34 * g * p * collapseState.cableDrop
}

/** Small travelling-wave vibration applied during the cascade phase. */
export function wobble(x: number, t: number): number {
  if (collapseState.cascade <= 0) return 0
  const a = Math.sin(x * 0.35 + t * 2.2) * 0.6 + Math.sin(x * 0.13 - t * 1.6) * 0.8
  return a * collapseState.cascade
}
