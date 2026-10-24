import { resolve } from 'node:path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'

const SERVICE_PORT = Number(process.env.VOICE_PARTNER_PORT || 3900)

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()]
  },
  preload: {
    plugins: [externalizeDepsPlugin()]
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
