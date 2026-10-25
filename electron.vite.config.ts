import { resolve } from 'node:path'
import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'

const SERVICE_PORT = Number(process.env.VOICE_PARTNER_PORT || 3900)

export default defineConfig({
  // electron-vite 6 externalizes dependencies by default; the option is spelled
  // out here because the old `externalizeDepsPlugin` helper is deprecated.
  main: {
    build: { externalizeDeps: true }
  },
  preload: {
    build: { externalizeDeps: true }
  },
  renderer: {
    root: resolve(process.cwd(), 'src/renderer'),
    plugins: [react()],
    server: {
      proxy: {
        // The renderer always calls /api/...; the service serves bare paths.
        '/api': {
          target: `http://127.0.0.1:${SERVICE_PORT}`,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, '')
        }
      }
    }
  }
})
