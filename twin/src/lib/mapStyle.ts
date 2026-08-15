import type { ExpressionSpecification } from 'maplibre-gl'
import { STATE_COLORS, NEUTRAL } from './theme'

/**
 * MapLibre style-spec match expression built from the shared palette so the
 * map paint can never desync from the 3D markers / gauge bands (line 83).
 * Unknown states render the same neutral grey `stateHex()` falls back to.
 *
 * Kept in a pure lib module (no maplibre runtime import) so unit tests can
 * validate the expression against the real style-spec validator without
 * pulling the browser map into the test runner (line 89).
 */
export function matchStateColor(): ExpressionSpecification {
  return [
    'match',
    ['get', 'state'],
    'RED', STATE_COLORS.RED,
    'AMBER', STATE_COLORS.AMBER,
    'GREEN', STATE_COLORS.GREEN,
    NEUTRAL,
  ]
}
