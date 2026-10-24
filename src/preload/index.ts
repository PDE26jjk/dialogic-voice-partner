import { contextBridge, ipcRenderer } from 'electron'

export interface ServiceStatus {
  state: 'starting' | 'ready' | 'failed' | 'stopped'
  detail: string
  port: number
  pid: number | null
}

contextBridge.exposeInMainWorld('voicepartner', {
  getServiceStatus: (): Promise<ServiceStatus> => ipcRenderer.invoke('service:get-status'),
  onServiceStatus: (callback: (status: ServiceStatus) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: ServiceStatus): void => {
      callback(status)
    }
    ipcRenderer.on('service:status', listener)
    return () => ipcRenderer.removeListener('service:status', listener)
  }
})
