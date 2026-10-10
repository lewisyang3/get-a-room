import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // GitHub Pages serves a project site under /<repo>/, so the deploy job sets
  // BASE_PATH. A custom domain serves it at the root, the default.
  base: process.env.BASE_PATH ?? '/',
  server: {
    // The API's default allowed CORS origin is http://localhost:3000, so the
    // dev server must not fall back to another port.
    port: 3000,
    strictPort: true,
    // Listen on all interfaces so the server is reachable from outside a
    // Docker container.
    host: true,
  },
  build: {
    // Mapbox GL is about 1.9 MB on its own. It's in a separate chunk that
    // loads only when the map is shown, so its size doesn't slow the page.
    chunkSizeWarningLimit: 2000,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // The map is required, so tests run as a configured site would. Pass
    // mapboxToken={null} to test an unconfigured one.
    env: { VITE_MAPBOX_TOKEN: 'pk.test' },
  },
})
