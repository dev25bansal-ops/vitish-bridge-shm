// One-time console breadcrumbs for silent-failure surfaces.
//
// The twin's four pollers + the WebSocket client swallow backend failures by
// design (honest offline/replay fallbacks, no UI spam).  But a broken backend
// should still be debuggable from the console: this logs the FIRST failure per
// key (console.warn), then stays silent — one breadcrumb per broken surface,
// never a flood.
const seen = new Set<string>()

export function warnOnce(key: string, message: string): void {
  if (seen.has(key)) return
  seen.add(key)
  console.warn(`[twin] ${message}`)
}
