export type VisitType = 'ilk_muayene' | 'kontrol' | 'konsultasyon' | 'acil'

export type SessionStatus =
  | 'NOT_STARTED'
  | 'RECORDING'
  | 'PROCESSING'
  | 'AWAITING_REVIEW'
  | 'COMPLETED'

export interface Session {
  id: number
  patient_id: string
  patient_name: string
  doctor_name: string
  visit_type: VisitType
  status: SessionStatus
  audio_file_path: string | null
  kvkk_consent: boolean
  started_at: string | null
  ended_at: string | null
  audio_duration_seconds: number | null
  created_at: string
  updated_at: string
}

export interface SessionDetail extends Session {
  segments: import('./transcription').TranscriptionSegment[]
  reports: import('./report').Report[]
}

export interface SessionListResponse {
  items: Session[]
  total: number
  page: number
  limit: number
  pages: number
}
