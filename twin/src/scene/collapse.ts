// Mutable damage state + box-girder geometry for the Z24 twin.
//
// Identity (D1-2): the hero bridge is the Z24 benchmark — a 14 + 30 + 14 m
// post-tensioned concrete box girder continuous over four supports.  The deck
// is 58 m total (x ∈ [-29, +29]), interior piers at x = ±14, first vertical
// mode f1 ≈ 3.8 Hz (healthy).  The mesh therefore renders a box girder — no
// towers, no cables.  The story's "collapse" is a mid-span stiffness loss:
// static deflection (sag) + exaggerated first-mode flexing (cascade).
//
// The mode shapes / frequencies are served by the backend physics overlay
// (GET /api/bridge/z24/stiffness → Euler-Bernoulli FEM) and read from the
// store.  Until the first snapshot arrives we fall back to the analytic
// reference simple-span mode φ1 = sin(π·x/30) over the main span.
import type { Scenario } from '../store'
import { useStore, F1_REF_HZ, BRIDGE_DECK_Y } from '../store'

export interface CollapseState {
  sag: number // 0..1 mid-span static deflection (damage)
  cascade: number // 0..1 first-mode flexing amplitude (exaggerated)
}

export const collapseState: CollapseState = {
  sag: 0,
  cascade: 0,
}

// Damage-tint saturation point for the main-span heat map — the deck tint
// reaches full saturation at this % EI stiffness loss, and the scene legend
// (SceneOverlay "35%+") labels the top of the ramp with the SAME number so the
// two can't desync.  Shared with MorbiBridge.segColor.
export const DAMAGE_SAT_PCT = 35

export const BRIDGE = {
  L: 58, // total superstructure length (14 + 30 + 14)
  half: 29,
  deckY: BRIDGE_DECK_Y, // deck soffit height above the river (store is the source)
  pierX: 14, // interior piers at x = ±14
  mainHalf: 15, // main (middle) span: x ∈ [-15, +15] = 30 m
  deckW: 5.4, // box-girder deck width (m)
  deckH: 1.6, // box-girder depth (m)
}

const T_ANIM_MAX = 15 // 15 s story arc (kept from the cable-stay bridge)
let animT = 0

const clamp01 = (v: number) => Math.max(0, Math.min(1, v))
const smooth = (x: number) => x * x * (3 - 2 * x)

function sync(): void {
  const t = Math.max(0, Math.min(T_ANIM_MAX, animT))
  // Deflection precedes flexing: the crack/onset droops first, then the
  // first-mode vibration builds up and stays (no flicker, no recovery).
  collapseState.sag = smooth(clamp01((t - 1.5) / 7.5))
  collapseState.cascade = smooth(clamp01((t - 4.5) / 10))
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

// --- geometry (pure; driven by the mutable collapseState + store) ------------

/** Interpolate the FEM first-mode shape (backend snapshot) at scene x. */
export function modePhi1(x: number): number {
  const st = useStore.getState()
  const s1 = st.stiffness.shapes[0]
  const fem = st.stiffness.x
  if (s1 && fem.length === s1.length) {
    // scene x ∈ [-29, +29] ↔ FEM x ∈ [0, 58]
    const xf = clamp01((x + BRIDGE.half) / BRIDGE.L) * (fem.length - 1)
    const i = Math.floor(xf)
    const j = Math.min(fem.length - 1, i + 1)
    const f = xf - i
    return (s1[i] ?? 0) * (1 - f) + (s1[j] ?? 0) * f
  }
  // Fallback: reference simple-span first mode over the 30 m main span.
  const xm = x / BRIDGE.mainHalf // -1..1 across the main span
  return Math.sin(Math.PI * (xm + 1) / 2)
}

/** Measured first vertical-mode frequency (Hz) from the physics overlay. */
export function modeFreq1(): number {
  const f = useStore.getState().stiffness.freqs[0]
  return f > 0 ? f : F1_REF_HZ
}

/**
 * Exaggerated first-mode flexing at scene x, time t.  `cascade` gates the
 * amplitude so a healthy deck is still; during damage the deck visibly bends
 * in its first mode at the *measured* f1.  Amplitude is exaggerated and the
 * overlay is labeled "mode shape · exaggerated" in the panel copy.
 */
export function wobble(x: number, t: number): number {
  if (collapseState.cascade <= 0) return 0
  const amp = 0.7 * collapseState.cascade * modePhi1(x)
  return amp * Math.sin(2 * Math.PI * modeFreq1() * t)
}

/** Deck soffit height at scene x (static base + mid-span damage droop).
 *
 * The droop is a VISUAL EXAGGERATION like the wobble: max 1.7 m of sag is far
 * beyond real deflection (mm–cm), amplified so the damage reads on screen.
 * The D2-9 caption ("deformation & mode flex exaggerated for visibility — not
 * to scale") covers it; keep this comment honest about the scale. */
export function deckYAt(x: number): number {
  // Static droop from the mid-span stiffness loss — a bell centred on the
  // main-span mid-point (x = 0), ~0 at the interior piers (x = ±14).
  const droop = 1.7 * Math.exp(-((x / 11) ** 2))
  return BRIDGE.deckY - collapseState.sag * droop
}
