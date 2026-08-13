import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITISH SHM digital twin dev server.
//  - /api  proxied to the FastAPI backend (port 8000)
//  - /ws   proxied to the WebSocket bridge (port 8765)
// The twin connects to the WS bridge directly via browser WebSocket;
// the proxy is a convenience fallback for same-origin deployments.
export default defineConfig({
  plugins: [react()],
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
