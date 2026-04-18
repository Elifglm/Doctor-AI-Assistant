export interface SUTItem {
  kodu: string
  adi: string
  brans: string
  ana_kategori: string
  alt_kategori: string
  puan: number
}

export interface SUTSearchResponse {
  results: SUTItem[]
  total: number
}

export interface SUTSuggestion {
  kodu: string
  adi: string
  brans: string
  confidence: number
  reasoning: string
}

export interface SUTSuggestResponse {
  suggestions: SUTSuggestion[]
}

export interface SUTConfirmedTetkik {
  kodu: string
  adi: string
  brans: string
}

export interface SUTOpenEMRSendRequest {
  session_id: number
  tetkikler: SUTConfirmedTetkik[]
  notes: string
}

export interface SUTOpenEMRSendResponse {
  success: boolean
  order_id: string
  patient_id: string
  sent_count: number
  filtered_count: number
  error: string
  doctor_brans: string
}
