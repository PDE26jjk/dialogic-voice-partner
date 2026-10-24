import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const SERVICE_PORT = Number(process.env.VOICE_PARTNER_PORT || 3900)

// Browser-only development entry: lets the UI run without the Electron shell.
export default defineConfig({
  root: resolve(process.cwd(), 'src/renderer'),
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${SERVICE_PORT}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
