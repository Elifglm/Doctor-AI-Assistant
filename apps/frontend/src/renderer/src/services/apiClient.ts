import { useAuthStore } from '../stores/authStore'

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
    username: string
    display_name: string
    role: string
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
      throw new Error('Oturum süresi doldu. Lütfen tekrar giriş yapın.')
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
      const error = await response.json().catch(() => ({ detail: 'Bir hata oluştu' }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }

    return response.json()
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: 'GET' })
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  delete<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: 'DELETE' })
  }
}

export const apiClient = new ApiClient()
