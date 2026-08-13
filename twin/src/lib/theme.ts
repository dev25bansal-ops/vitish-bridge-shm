import type { HealthState } from '../store'

// Shared palette — one source of truth for the state -> color mapping used by
// the 3D markers, the map and the gauge bands.
export const STATE_COLORS: Record<HealthState, string> = {
  GREEN: '#22c55e',
  AMBER: '#f59e0b',
  RED: '#ef4444',
}

export const ACCENT = '#38bdf8'

export function stateHex(state: HealthState): string {
  return STATE_COLORS[state] ?? '#7c8ea0'
}
