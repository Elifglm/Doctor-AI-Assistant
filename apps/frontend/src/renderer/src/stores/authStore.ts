import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { useSessionStore } from './sessionStore'
import { useTranscriptionStore } from './transcriptionStore'

interface UserInfo {
  username: string
  display_name: string
  role: string
  brans: string
}

interface AuthState {
  token: string | null
  tokenExpiresAt: number | null
  user: UserInfo | null
  isAuthenticated: boolean
  setAuth: (token: string, user: UserInfo, expiresIn: number) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      tokenExpiresAt: null,
      user: null,
      isAuthenticated: false,
      setAuth: (token, user, expiresIn) =>
        set({
          token,
          user,
          isAuthenticated: true,
          tokenExpiresAt: Date.now() + expiresIn * 1000,
        }),
      logout: () => {
        useSessionStore.getState().reset()
        useTranscriptionStore.getState().reset()
        set({ token: null, tokenExpiresAt: null, user: null, isAuthenticated: false })
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
)
