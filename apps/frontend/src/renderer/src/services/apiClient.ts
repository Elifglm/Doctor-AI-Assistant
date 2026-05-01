import { useAuthStore } from '../stores/authStore'
import { t } from '../lib/i18n'

const getBaseUrl = (): string => {
  if (typeof window !== 'undefined' && window.electronAPI) {
    return window.electronAPI.getBackendUrl()
  }
  return 'http://127.0.0.1:8700'
}

/** Refresh the token 5 minutes before it expires. */
const REFRESH_BUFFER_MS = 5 * 60 * 1000

interface TokenRefreshResponse {
  access_token: string
  expires_in: number
  user: {
    id: number
    username: string
    display_name: string
    role: string
    brans: string
  }
}

class ApiClient {
  private baseUrl: string
  private refreshTimer: ReturnType<typeof setTimeout> | null = null
  private isRefreshing = false

  constructor() {
    this.baseUrl = getBaseUrl()
    this.scheduleTokenRefresh()

    // Re-schedule whenever the auth state changes (e.g. after login)
    useAuthStore.subscribe((state, prevState) => {
      if (state.tokenExpiresAt !== prevState.tokenExpiresAt) {
        this.scheduleTokenRefresh()
      }
    })
  }

  /**
   * Schedule a token refresh to fire 5 minutes before the current
   * token expires.  If the refresh endpoint call fails, the user
   * is logged out.
   */
  private scheduleTokenRefresh(): void {
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer)
      this.refreshTimer = null
    }

    const { tokenExpiresAt, isAuthenticated } = useAuthStore.getState()
    if (!isAuthenticated || !tokenExpiresAt) return

    const msUntilExpiry = tokenExpiresAt - Date.now()

    // If the token has already expired, log out immediately
    if (msUntilExpiry <= 0) {
      useAuthStore.getState().logout()
      return
    }

    // Fire the refresh REFRESH_BUFFER_MS before expiry (min 0)
    const delay = Math.max(msUntilExpiry - REFRESH_BUFFER_MS, 0)

    this.refreshTimer = setTimeout(() => {
      void this.refreshToken()
    }, delay)
  }

  private async refreshToken(): Promise<void> {
    if (this.isRefreshing) return
    this.isRefreshing = true

    try {
      const response = await this.post<TokenRefreshResponse>('/api/v1/auth/refresh')
      const { setAuth } = useAuthStore.getState()
      setAuth(response.access_token, response.user, response.expires_in)
      // scheduleTokenRefresh is triggered automatically by the subscribe callback
    } catch {
      // Refresh failed -- token may be expired or backend unreachable.
      // Log the user out for security.
      useAuthStore.getState().logout()
    } finally {
      this.isRefreshing = false
    }
  }

  private getHeaders(): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    const token = useAuthStore.getState().token
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    return headers
  }

  async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    // Check client-side token expiry before making a request
    const { tokenExpiresAt, isAuthenticated } = useAuthStore.getState()
    if (isAuthenticated && tokenExpiresAt && Date.now() >= tokenExpiresAt) {
      useAuthStore.getState().logout()
      throw new Error(t('err_sessionExpired'))
    }

    const url = `${this.baseUrl}${path}`
    const response = await fetch(url, {
      ...options,
      headers: { ...this.getHeaders(), ...options.headers },
    })

    if (!response.ok) {
      if (response.status === 401) {
        useAuthStore.getState().logout()
      }
      const error = await response.json().catch(() => ({ detail: t('err_generic') }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }

    return response.json()
  }

  get<T>(path: string, options: { signal?: AbortSignal } = {}): Promise<T> {
    return this.request<T>(path, { method: 'GET', signal: options.signal })
  }

  post<T>(path: string, body?: unknown, options: { signal?: AbortSignal } = {}): Promise<T> {
    return this.request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
      signal: options.signal,
    })
  }

  put<T>(path: string, body?: unknown, options: { signal?: AbortSignal } = {}): Promise<T> {
    return this.request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
      signal: options.signal,
    })
  }

  patch<T>(path: string, body?: unknown, options: { signal?: AbortSignal } = {}): Promise<T> {
    return this.request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
      signal: options.signal,
    })
  }

  delete<T>(path: string, options: { signal?: AbortSignal } = {}): Promise<T> {
    return this.request<T>(path, { method: 'DELETE', signal: options.signal })
  }
}

export const apiClient = new ApiClient()
