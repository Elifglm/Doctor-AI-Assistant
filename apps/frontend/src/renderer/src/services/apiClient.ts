import { useAuthStore } from '../stores/authStore'

const getBaseUrl = (): string => {
  if (typeof window !== 'undefined' && window.electronAPI) {
    return window.electronAPI.getBackendUrl()
  }
  return 'http://127.0.0.1:8700'
}

class ApiClient {
  private baseUrl: string

  constructor() {
    this.baseUrl = getBaseUrl()
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
    const url = `${this.baseUrl}${path}`
    const response = await fetch(url, {
      ...options,
      headers: { ...this.getHeaders(), ...options.headers },
    })

    if (!response.ok) {
      if (response.status === 401) {
        useAuthStore.getState().logout()
      }
      const error = await response.json().catch(() => ({ detail: 'Bir hata olustu' }))
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
