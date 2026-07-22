import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite dev server for the trip-planner frontend.
// The backend runs separately on :8000. Proxy API calls through Vite.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Forward all API calls to backend; Vite serves the SPA source itself.
      '/plan': 'http://localhost:8000',
      '/booking': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/agents': 'http://localhost:8000',
    },
  },
})
