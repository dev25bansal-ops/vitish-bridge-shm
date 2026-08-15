import type { HealthState } from '../store'

// Shared palette — one source of truth for the state -> color mapping used by
// the 3D markers, the map and the gauge bands.
//
// LIGHT theme (clean, projector-safe).  The traffic-light states are deepened
// (600-series) so they keep WCAG-AA text contrast on the white panels while
// staying vivid enough to read from the back of a demo room.  The accent is a
// deep engineering teal — deliberately NOT the default government blue, so the
// warnings (amber/red) stay the most salient thing on screen.
export const STATE_COLORS: Record<HealthState, string> = {
  GREEN: '#16a34a',
  AMBER: '#d97706',
  RED: '#dc2626',
}

export const ACCENT = '#0d9488' // teal-600 · swap to '#2563eb' for a blue accent

/** Neutral grey for any state the twin hasn't been taught to color. */
export const NEUTRAL = '#7c8ea0'

export function stateHex(state: HealthState): string {
  return STATE_COLORS[state] ?? NEUTRAL
}
