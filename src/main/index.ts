import { app, BrowserWindow, ipcMain } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { join } from 'node:path'

const SERVICE_PORT = Number(process.env.VOICE_PARTNER_PORT || 3900)
const SERVICE_URL = `http://127.0.0.1:${SERVICE_PORT}`
const READY_TIMEOUT_MS = 120_000

type ServiceState = 'starting' | 'ready' | 'failed' | 'stopped'

interface ServiceStatus {
  state: ServiceState
  detail: string
  port: number
  pid: number | null
}

let status: ServiceStatus = {
  state: 'starting',
  detail: 'Starting the local service',
  port: SERVICE_PORT,
  pid: null
}

let service: ChildProcess | null = null
let shutdownRequested = false

function projectRoot(): string {
  return app.isPackaged ? process.resourcesPath : process.cwd()
}

function publish(next: Partial<ServiceStatus>): void {
  status = { ...status, ...next }
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send('service:status', status)
  }
}

async function waitForHealth(): Promise<boolean> {
  const deadline = Date.now() + READY_TIMEOUT_MS
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${SERVICE_URL}/health`)
      if (response.ok) return true
    } catch {
      // The service is not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  return false
}

async function startService(): Promise<void> {
  const root = projectRoot()
  const serviceDir = join(root, 'service')
  publish({ state: 'starting', detail: 'Starting the local service', pid: null })

  service = spawn(
    'uv',
    [
      'run',
      '--project',
      serviceDir,
      'uvicorn',
      'app.main:app',
      '--app-dir',
      serviceDir,
      '--host',
      '127.0.0.1',
      '--port',
      String(SERVICE_PORT)
    ],
    {
      cwd: root,
      windowsHide: true,
      env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1' }
    }
  )

  service.stdout?.on('data', (chunk) => process.stdout.write(`[service] ${chunk}`))
  service.stderr?.on('data', (chunk) => process.stderr.write(`[service] ${chunk}`))
  service.on('exit', (code) => {
    if (shutdownRequested) return
    publish({ state: 'failed', detail: `Service exited with code ${code ?? 'unknown'}`, pid: null })
  })

  if (await waitForHealth()) {
    publish({ state: 'ready', detail: 'Service ready', pid: service.pid ?? null })
  } else {
    publish({ state: 'failed', detail: 'Service did not become ready in time', pid: null })
  }
}

function stopService(): void {
  shutdownRequested = true
  if (!service || service.killed) return
  if (process.platform === 'win32' && service.pid) {
    spawn('taskkill', ['/pid', String(service.pid), '/T', '/F'], { windowsHide: true })
  } else {
    service.kill('SIGTERM')
  }
  service = null
}

function createWindow(): void {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    title: 'Dialogic Voice Partner',
    backgroundColor: '#12141a',
    // The renderer draws its own title bar, so the native frame is hidden.
    frame: false,
    titleBarStyle: 'hidden',
    trafficLightPosition: { x: 12, y: 12 },
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  })

  const publishMaximized = (): void => {
    window.webContents.send('window:maximized', window.isMaximized())
  }
  window.on('maximize', publishMaximized)
  window.on('unmaximize', publishMaximized)

  if (process.env.ELECTRON_RENDERER_URL) {
    void window.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void window.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

ipcMain.handle('service:get-status', () => status)

function windowOf(event: Electron.IpcMainInvokeEvent): BrowserWindow | null {
  return BrowserWindow.fromWebContents(event.sender)
}

ipcMain.handle('window:minimize', (event) => windowOf(event)?.minimize())
ipcMain.handle('window:toggle-maximize', (event) => {
  const window = windowOf(event)
  if (!window) return false
  if (window.isMaximized()) {
    window.unmaximize()
  } else {
    window.maximize()
  }
  return window.isMaximized()
})
ipcMain.handle('window:close', (event) => windowOf(event)?.close())
ipcMain.handle('window:is-maximized', (event) => windowOf(event)?.isMaximized() ?? false)

app.whenReady().then(() => {
  createWindow()
  void startService()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stopService()
})
