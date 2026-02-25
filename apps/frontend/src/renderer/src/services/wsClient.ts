type MessageHandler = (data: unknown) => void

export class WSClient {
  private ws: WebSocket | null = null
  private url: string
  private handlers: Map<string, MessageHandler[]> = new Map()
  private _reconnectAttempts = 0
  private readonly maxReconnectAttempts = 3

  constructor(url: string) {
    this.url = url
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this._reconnectAttempts >= this.maxReconnectAttempts) {
        reject(new Error('Max reconnect attempts reached'))
        return
      }

      this.ws = new WebSocket(this.url)
      this.ws.binaryType = 'arraybuffer'

      this.ws.onopen = () => {
        this._reconnectAttempts = 0
        resolve()
      }

      this.ws.onerror = (error) => {
        reject(error)
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

      this.ws.onclose = () => {
        this.ws = null
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
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.handlers.clear()
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}
