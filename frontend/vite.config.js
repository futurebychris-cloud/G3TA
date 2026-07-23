import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite dev server for the trip-planner frontend.
// The backend runs separately on :8000. Proxy API calls through Vite.
export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: {
    port: 5173,
    allowedHosts: true,
    proxy: {
      // Forward all API calls to backend; Vite serves the SPA source itself.
      '/plan': 'http://localhost:8000',
      '/booking': 'http://localhost:8000',
      '/intake': 'http://localhost:8000',
      '/speech': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/agents': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: true,
  },
})
