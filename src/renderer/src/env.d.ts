/// <reference types="vite/client" />

export interface ServiceStatus {
  state: 'starting' | 'ready' | 'failed' | 'stopped'
  detail: string
  port: number
  pid: number | null
}

export interface VoicePartnerBridge {
  getServiceStatus(): Promise<ServiceStatus>
  onServiceStatus(callback: (status: ServiceStatus) => void): () => void
  minimize(): Promise<void>
  toggleMaximize(): Promise<boolean>
  close(): Promise<void>
  isMaximized(): Promise<boolean>
  onMaximizedChange(callback: (maximized: boolean) => void): () => void
}

declare global {
  interface Window {
    voicepartner?: VoicePartnerBridge
  }
}
