import { useAuthStore } from '../stores/authStore'

export interface SSEEvent {
  event: string
  data: Record<string, unknown>
}

export type SSEEventHandler = (event: SSEEvent) => void

/**
 * SSE client for streaming LLM report generation.
 *
 * Uses fetch + ReadableStream instead of EventSource because EventSource
 * does not support custom headers (Authorization).
 */
export class SSEClient {
  private abortController: AbortController | null = null

  async connect(
    url: string,
    onEvent: SSEEventHandler,
    onError?: (error: Error) => void,
    onComplete?: () => void
  ): Promise<void> {
    this.close()
    this.abortController = new AbortController()

    const token = useAuthStore.getState().token
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers,
        signal: this.abortController.signal,
      })

      if (!response.ok) {
        throw new Error(`SSE connection failed: HTTP ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('SSE response body is not readable')
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = 'message'

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            const dataStr = line.slice(5).trim()
            try {
              const data = JSON.parse(dataStr) as Record<string, unknown>
              onEvent({ event: currentEvent, data })
            } catch {
              onEvent({ event: currentEvent, data: { raw: dataStr } })
            }
            currentEvent = 'message'
          }
        }
      }

      onComplete?.()
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return
      }
      onError?.(err instanceof Error ? err : new Error(String(err)))
    }
  }

  close(): void {
    if (this.abortController) {
      this.abortController.abort()
      this.abortController = null
    }
  }
}
