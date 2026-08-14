// D2-7 georeferenced context config.  The Cesium ion token lives in twin/.env
// (gitignored) and is injected by Vite as VITE_CESIUM_TOKEN.  We only ever use
// the token inside the browser (client-side), never print it, never commit it.
//
// The hero bridge is the Z24 post-tensioned box girder (Swiss reference).  The
// real Z24 carried the A1 motorway near Nottwil, Switzerland during the
// 1998-99 EMPA campaign — so the georeferenced view frames THAT reference site
// (honest), while the structure itself is our modeled digital shadow.
export const GEO_TOKEN: string | undefined =
  (import.meta.env.VITE_CESIUM_TOKEN as string | undefined) || undefined

export const GEO_READY = Boolean(GEO_TOKEN)

/** Z24 reference site (real-world location of the monitored bridge). */
export const Z24_SITE = {
  name: 'Z24 reference site · Nottwil, CH (A1)',
  lat: 47.135,
  lng: 8.165,
  /** meters above mean sea level to anchor the box-girder deck. */
  height: 540,
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
  // fly to ~550 m AGL, looking down at the bridge from the south
  distance: 550,
  pitchDeg: -28,
  headingDeg: 0,
} as const
