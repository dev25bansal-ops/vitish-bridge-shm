import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import cesium from 'vite-plugin-cesium'

// VITISH SHM digital twin dev server.
//  - /api  proxied to the FastAPI backend (default port 8000)
//  - /ws   proxied to the WebSocket bridge (default port 8765)
// The twin normally connects DIRECTLY to the backend via src/lib/config.ts
// (discovered ports from GET /api/config, VITE_API_BASE/VITE_WS_URL overrides,
// then localhost defaults).  These proxies are only a convenience for
// same-origin deployments where the browser reaches the twin's own origin.
//  - cesium() copies the CesiumJS static assets (Workers/Assets/Widgets) and
//    sets CESIUM_BASE_URL, powering the D2-7 georeferenced context view.
export default defineConfig({
  plugins: [react(), cesium()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8765',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 1600,
  },
})
