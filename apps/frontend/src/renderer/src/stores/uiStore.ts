import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'light' | 'dark'

interface UIState {
  theme: Theme
  sidebarOpen: boolean
  fontSize: number
  locale: 'tr' | 'en'
  activeModal: string | null
  setTheme: (theme: Theme) => void
  toggleSidebar: () => void
  setFontSize: (size: number) => void
  setLocale: (locale: 'tr' | 'en') => void
  openModal: (id: string) => void
  closeModal: () => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      theme: 'light',
      sidebarOpen: true,
      fontSize: 16,
      locale: 'tr',
      activeModal: null,
      setTheme: (theme) => set({ theme }),
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setFontSize: (fontSize) => set({ fontSize }),
      setLocale: (locale) => set({ locale }),
      openModal: (id) => set({ activeModal: id }),
      closeModal: () => set({ activeModal: null }),
    }),
    { name: 'ui-storage' }
  )
)
