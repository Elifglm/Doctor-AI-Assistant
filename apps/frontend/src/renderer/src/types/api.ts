export interface ApiError {
  detail: string
  status_code: number
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'error'
  gpu_available: boolean
  gpu_name?: string
  gpu_memory_used_mb?: number
  gpu_memory_total_mb?: number
  db_connected: boolean
  asr_pipeline_ready: boolean
  ollama_status: 'connected' | 'disconnected' | 'unknown'
  ollama_model_loaded: boolean
  rag_doc_count: number
  version: string
}
