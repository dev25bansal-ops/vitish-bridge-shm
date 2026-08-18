// PERF-07: the GeoContext layout chunk.  Keeps the Cesium-globe subtree out of
// the initial twin bundle (Cesium is a ~30 MB package; GeoContext already lazy-
// imports the library, so this module is a thin wrapper that simply re-exports
// the view).  App.tsx lazy-loads this chunk — the wrapper plus GeoContext's own
// `import('cesium')` split the heavy globe work from first paint entirely.
import { GeoContext } from './GeoContext'

export { GeoContext }