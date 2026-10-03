import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The API's default allowed CORS origin is http://localhost:3000, so the
    // dev server must not fall back to another port.
    port: 3000,
    strictPort: true,
    // Listen on all interfaces so the server is reachable from outside a
    // Docker container.
    host: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
