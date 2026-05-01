import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'light' | 'dark'

interface UIState {
  theme: Theme
  sidebarOpen: boolean
  fontSize: number
  locale: 'tr' | 'en'
  activeModal: string | null
  micDeviceId: string | null
  setTheme: (theme: Theme) => void
  toggleSidebar: () => void
  setFontSize: (size: number) => void
  setLocale: (locale: 'tr' | 'en') => void
  openModal: (id: string) => void
  closeModal: () => void
  setMicDeviceId: (deviceId: string | null) => void
}

function applyTheme(theme: Theme): void {
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

function applyFontSize(size: number): void {
  document.documentElement.style.fontSize = `${size}px`
}

function applyLocale(locale: 'tr' | 'en'): void {
  document.documentElement.lang = locale
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      theme: 'light',
      sidebarOpen: true,
      fontSize: 16,
      locale: 'tr',
      activeModal: null,
      micDeviceId: null,
      setTheme: (theme) => {
        applyTheme(theme)
        set({ theme })
      },
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setFontSize: (fontSize) => {
        applyFontSize(fontSize)
        set({ fontSize })
      },
      setLocale: (locale) => {
        applyLocale(locale)
        set({ locale })
      },
      openModal: (id) => set({ activeModal: id }),
      closeModal: () => set({ activeModal: null }),
      setMicDeviceId: (micDeviceId) => set({ micDeviceId }),
    }),
    {
      name: 'ui-storage',
      onRehydrateStorage: () => (state) => {
        if (state?.theme) {
          applyTheme(state.theme)
        }
        if (state?.fontSize) {
          applyFontSize(state.fontSize)
        }
        if (state?.locale) {
          applyLocale(state.locale)
        }
      },
    }
  )
)
