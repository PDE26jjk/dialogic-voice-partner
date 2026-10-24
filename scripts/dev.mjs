import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Some agent/tool environments export ELECTRON_RUN_AS_NODE=1 for unrelated
// tooling. If it leaks into the Electron child, the app starts as a plain Node
// process and fails on the first `require('electron')` API access.
const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const cli = join(root, 'node_modules', 'electron-vite', 'bin', 'electron-vite.js')

const child = spawn(process.execPath, [cli, 'dev'], {
  cwd: root,
  stdio: 'inherit',
  env
})

child.on('exit', (code) => process.exit(code ?? 0))
