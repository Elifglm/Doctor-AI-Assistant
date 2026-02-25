import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { useSessionStore } from './sessionStore'
import { useTranscriptionStore } from './transcriptionStore'

interface UserInfo {
  username: string
  display_name: string
  role: string
}

interface AuthState {
  token: string | null
  user: UserInfo | null
  isAuthenticated: boolean
  setAuth: (token: string, user: UserInfo) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      setAuth: (token, user) => set({ token, user, isAuthenticated: true }),
      logout: () => {
        // Clean up all stores on logout
        useSessionStore.getState().reset()
        useTranscriptionStore.getState().reset()
        set({ token: null, user: null, isAuthenticated: false })
      },
    }),
    { name: 'auth-storage' }
  )
)
