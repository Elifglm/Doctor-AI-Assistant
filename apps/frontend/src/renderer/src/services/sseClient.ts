// Placeholder for future LLM streaming
export class SSEClient {
  private eventSource: EventSource | null = null

  connect(url: string, onMessage: (data: unknown) => void, onError?: (error: Event) => void): void {
    this.eventSource = new EventSource(url)

    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch {
        onMessage(event.data)
      }
    }

    if (onError) {
      this.eventSource.onerror = onError
    }
  }

  close(): void {
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = null
    }
  }
}
