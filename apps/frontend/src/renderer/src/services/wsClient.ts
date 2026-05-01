import { t } from '../lib/i18n'

type MessageHandler = (data: unknown) => void

/**
 * Global registry of active WSClient connections keyed by URL.
 * Prevents multiple tabs/components from opening duplicate WebSocket
 * connections to the same session endpoint.
 */
const _activeClients: Map<string, WSClient> = new Map()

/** Delay between reconnect attempts (doubles each time). */
const BASE_RECONNECT_DELAY_MS = 1000

export class WSClient {
  private ws: WebSocket | null = null
  private url: string
  private handlers: Map<string, MessageHandler[]> = new Map()
  private _reconnectAttempts = 0
  private readonly maxReconnectAttempts = 3
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null
  /** Set to true after a successful connection + intentional close. */
  private _intentionallyClosed = false

  constructor(url: string) {
    this.url = url
  }

  connect(): Promise<void> {
    this._intentionallyClosed = false

    return new Promise((resolve, reject) => {
      // Guard: prevent duplicate connections to the same session URL
      const existing = _activeClients.get(this.url)
      if (existing && existing !== this) {
        if (existing.isConnected) {
          reject(new Error(t('err_wsAlreadyConnected')))
          return
        }
        // Stale entry -- remove it and proceed
        existing.close()
        _activeClients.delete(this.url)
      }

      // Guard: this instance is already connected
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        reject(new Error(t('err_wsAlready')))
        return
      }

      if (this._reconnectAttempts >= this.maxReconnectAttempts) {
        reject(new Error(t('err_wsMaxReconnect')))
        return
      }

      // Register eagerly so any concurrent connect() sees this instance
      _activeClients.set(this.url, this)

      this.ws = new WebSocket(this.url)
      this.ws.binaryType = 'arraybuffer'

      this.ws.onopen = () => {
        this._reconnectAttempts = 0
        resolve()
      }

      this.ws.onerror = () => {
        _activeClients.delete(this.url)
        reject(new Error(t('err_wsConnect', { url: this.url })))
      }

      this.ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          try {
            const data = JSON.parse(event.data)
            const type = data.type as string
            const handlers = this.handlers.get(type) || []
            handlers.forEach((handler) => handler(data))
            // Also emit to wildcard handlers
            const allHandlers = this.handlers.get('*') || []
            allHandlers.forEach((handler) => handler(data))
          } catch {
            console.error('Failed to parse WebSocket message')
          }
        }
      }

      this.ws.onclose = (event) => {
        this.ws = null
        _activeClients.delete(this.url)

        // Normal closure (code 1000) or intentional close -- no retry
        if (event.code === 1000 || this._intentionallyClosed) {
          const closeHandlers = this.handlers.get('close') || []
          closeHandlers.forEach((handler) => handler({ code: event.code, reason: event.reason }))
          return
        }

        // Unexpected disconnection -- attempt auto-reconnect
        this._reconnectAttempts++

        if (this._reconnectAttempts < this.maxReconnectAttempts) {
          const delay = BASE_RECONNECT_DELAY_MS * this._reconnectAttempts
          this._reconnectTimer = setTimeout(() => {
            this.connect().catch(() => {
              // Reconnection failed -- close handlers already emitted by inner call
            })
          }, delay)
        } else {
          // Max attempts exceeded -- emit close with error info
          const closeHandlers = this.handlers.get('close') || []
          closeHandlers.forEach((handler) =>
            handler({
              code: event.code,
              reason: t('err_wsDisconnected'),
            })
          )
        }
      }
    })
  }

  on(type: string, handler: MessageHandler): () => void {
    const existing = this.handlers.get(type) || []
    this.handlers.set(type, [...existing, handler])
    return () => {
      const handlers = this.handlers.get(type) || []
      this.handlers.set(type, handlers.filter((h) => h !== handler))
    }
  }

  sendBinary(data: ArrayBuffer | Blob): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data)
    }
  }

  sendJSON(data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  close(): void {
    this._intentionallyClosed = true
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer)
      this._reconnectTimer = null
    }
    _activeClients.delete(this.url)
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.handlers.clear()
    this._reconnectAttempts = 0
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}
