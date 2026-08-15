// D2-7 georeferenced context config.  The Cesium ion token lives in twin/.env
// (gitignored) and is injected by Vite as VITE_CESIUM_TOKEN.  We only ever use
// the token inside the browser (client-side), never print it, never commit it.
//
// The hero bridge is the Z24 post-tensioned box girder (Swiss reference).  The
// real Z24 was a 14+30+14 m overpass carrying the Koppigen–Utzenstorf road
// across the A1 motorway (Bern–Zürich) near Koppigen, canton Bern, instrumented
// during the 1998-99 EMPA/KU Leuven campaign and demolished in 1999.  The
// bridge itself no longer exists, so the georeferenced view frames the real A1
// corridor between Koppigen and Utzenstorf as the reference site (honest: the
// terrain/buildings are real, the structure is our modeled digital shadow).
// Coordinates are schematic — anchored to the A1 between the two villages
// (both ~47.133°N; Koppigen 7.600°E, Utzenstorf 7.550°E), not a surveyed site.
export const GEO_TOKEN: string | undefined =
  (import.meta.env.VITE_CESIUM_TOKEN as string | undefined) || undefined

export const GEO_READY = Boolean(GEO_TOKEN)

/** Z24 reference site (real A1 corridor near the former bridge, Koppigen, CH). */
export const Z24_SITE = {
  name: 'Z24 reference site · A1 near Koppigen, CH',
  lat: 47.136,
  lng: 7.578,
  /** Deck elevation (m MSL) — schematic.  Ground at this point measures ~539 m
   *  on World Terrain once loaded, so the deck sits ~16 m above it (a tall
   *  overpass, visually correct for the A1 crossing).  Kept constant instead of
   *  runtime-sampled: Cesium's getHeight() returns garbage for many seconds
   *  before the terrain tile under the site loads, so sampling is unreliable. */
  height: 555,
  /** deck axis bearing (deg, clockwise from north) — schematic, not surveyed. */
  headingDeg: -35,
} as const

/** Real Z24 geometry used to size the modeled shadow (14+30+14 m spans). */
export const Z24_BOX = {
  length: 58, // 14 + 30 + 14
  width: 8,
  depth: 2.2,
} as const

/** Deck sensor nodes in the same local frame as the twin's sensors (x = along span). */
export const GEO_NODE_OFFSETS = [-10, 0, 10] as const

/** Local-frame heading/pitch/roll helper shared with the viewer. */
export const GEO_CAMERA = {
  // Frame the 58 m deck at a readable size while keeping the real terrain
  // (A1 corridor) as context: ~300 m out, pitched ~30° down from the south.
  distance: 300,
  pitchDeg: -30,
  headingDeg: 0,
} as const
