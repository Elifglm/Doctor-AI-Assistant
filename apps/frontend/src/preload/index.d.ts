export interface ElectronAPI {
  getBackendUrl: () => string
  getAppVersion: () => Promise<string>
  showFloatingWindow: () => Promise<void>
  hideFloatingWindow: () => Promise<void>
  platform: string
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
