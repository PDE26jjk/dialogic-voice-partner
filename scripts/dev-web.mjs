import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Runs the local service plus a plain Vite dev server, so the UI can be opened
// in a browser when the Electron shell cannot start (for example while a
// system-level overlay driver is being investigated).
const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE

const port = Number(process.env.VOICE_PARTNER_PORT || 3900)

const service = spawn(
  'uv',
  [
    'run',
    '--project',
    join(root, 'service'),
    'uvicorn',
    'app.main:app',
    '--app-dir',
    join(root, 'service'),
    '--host',
    '127.0.0.1',
    '--port',
    String(port)
  ],
  { cwd: root, stdio: 'inherit', env }
)

const vite = spawn(
  process.execPath,
  [join(root, 'node_modules', 'vite', 'bin', 'vite.js'), '--config', 'vite.web.config.mts'],
  { cwd: root, stdio: 'inherit', env }
)

function shutdown(code = 0) {
  service.kill()
  vite.kill()
  process.exit(code)
}

process.on('SIGINT', () => shutdown(0))
vite.on('exit', (code) => shutdown(code ?? 0))
service.on('exit', (code) => {
  if (code && code !== 0) shutdown(code)
})
