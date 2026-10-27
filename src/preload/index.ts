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
  },
  minimize: (): Promise<void> => ipcRenderer.invoke('window:minimize'),
  toggleMaximize: (): Promise<boolean> => ipcRenderer.invoke('window:toggle-maximize'),
  close: (): Promise<void> => ipcRenderer.invoke('window:close'),
  isMaximized: (): Promise<boolean> => ipcRenderer.invoke('window:is-maximized'),
  onMaximizedChange: (callback: (maximized: boolean) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, maximized: boolean): void => {
      callback(maximized)
    }
    ipcRenderer.on('window:maximized', listener)
    return () => ipcRenderer.removeListener('window:maximized', listener)
  }
})
