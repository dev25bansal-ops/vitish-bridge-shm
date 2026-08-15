import { defineConfig } from 'vitest/config'

// Unit tests for the twin (line 89).  Every module under test is pure TS or
// zustand-store logic that runs in plain Node — no DOM environment needed.
// The ws.ts state-machine test stubs `window`/`WebSocket` itself.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
