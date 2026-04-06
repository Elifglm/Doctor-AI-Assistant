export interface TranscriptionSegment {
  id: number
  session_id: number
  segment_index: number
  text: string
  speaker: string
  speaker_label: string
  start_time: number
  end_time: number
  confidence: number | null
  words: Record<string, unknown>[] | null
  is_edited: boolean
}

export interface TranscriptionResponse {
  session_id: number
  segments: TranscriptionSegment[]
  full_text: string
  duration_seconds: number
  num_speakers: number
}

export interface WSProgress {
  type: 'progress'
  stage: string
  message: string
  progress?: number
}

export interface WSResult {
  type: 'result'
  session_id: number
  segments: TranscriptionSegment[]
  full_text: string
  metadata: Record<string, unknown>
}

export interface WSError {
  type: 'error'
  message: string
  code: string
}

export interface WSProcessingStart {
  type: 'processing_start'
  message: string
}

export type WSMessage = WSProgress | WSResult | WSError | WSProcessingStart
