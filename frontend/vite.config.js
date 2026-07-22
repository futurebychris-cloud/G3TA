import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite dev server for the trip-planner frontend.
// The backend runs separately on :8000 (see VITE_API_BASE in .env.example).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: true,
  },
})
