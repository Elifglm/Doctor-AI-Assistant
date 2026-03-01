import { create } from 'zustand'
import { persist, type StateStorage } from 'zustand/middleware'
import { useSessionStore } from './sessionStore'
import { useTranscriptionStore } from './transcriptionStore'

interface UserInfo {
  username: string
  display_name: string
  role: string
}

interface AuthState {
  token: string | null
  /** Token expiry timestamp in milliseconds (epoch). Set on login. */
  tokenExpiresAt: number | null
  user: UserInfo | null
  isAuthenticated: boolean
  setAuth: (token: string, user: UserInfo, expiresIn: number) => void
  logout: () => void
}

/**
 * Custom storage adapter that Base64-encodes persisted state.
 * This prevents casual reading of the JWT token stored in localStorage.
 * NOTE: Base64 is NOT encryption -- it only provides obfuscation.
 * A production app should use OS-level credential storage (e.g. keytar).
 */
const obfuscatedStorage: StateStorage = {
  getItem: (name: string): string | null => {
    const raw = localStorage.getItem(name)
    if (!raw) return null
    try {
      return atob(raw)
    } catch {
      // If decoding fails, the value may be from before the migration.
      // Clear it so the user re-authenticates cleanly.
      localStorage.removeItem(name)
      return null
    }
  },
  setItem: (name: string, value: string): void => {
    localStorage.setItem(name, btoa(value))
  },
  removeItem: (name: string): void => {
    localStorage.removeItem(name)
  },
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
        // Clean up all stores on logout
        useSessionStore.getState().reset()
        useTranscriptionStore.getState().reset()
        set({ token: null, tokenExpiresAt: null, user: null, isAuthenticated: false })
      },
    }),
    {
      name: 'auth-storage',
      storage: obfuscatedStorage,
    }
  )
)
