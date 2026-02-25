import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendUrl: () => 'http://127.0.0.1:8700',
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  showFloatingWindow: () => ipcRenderer.invoke('show-floating-window'),
  hideFloatingWindow: () => ipcRenderer.invoke('hide-floating-window'),
  platform: process.platform
})
