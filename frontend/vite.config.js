import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite dev server for the trip-planner frontend.
// The backend runs separately on :8000. Proxy API calls through Vite.
export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: {
    port: 5173,
    proxy: {
      // Forward all API calls to backend; Vite serves the SPA source itself.
      '/plan': 'http://127.0.0.1:8000',
      '/booking': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/agents': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: true,
  },
})
