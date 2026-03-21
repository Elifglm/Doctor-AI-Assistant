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
  llm_mode: 'local' | 'api'
  llm_provider: 'ollama' | 'gemini'
  llm_model_name: string
}

export interface LLMSettingsResponse {
  mode: 'local' | 'api'
  ollama_url: string
  ollama_model: string
  ollama_fallback_model: string
  ollama_fallback_enabled: boolean
  gemini_model: string
  gemini_api_key_set: boolean
  temperature: number
  top_p: number
  max_tokens: number
}

export interface LLMSettingsUpdate {
  mode?: 'local' | 'api'
  gemini_api_key?: string
  gemini_model?: string
  ollama_fallback_enabled?: boolean
  temperature?: number
  top_p?: number
  max_tokens?: number
}
