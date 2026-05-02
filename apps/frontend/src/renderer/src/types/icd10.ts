export interface ICD10Item {
  icd_kodu: string
  tani: string
  ust_kod: string | null
  seviye: number
}

export interface ICD10SearchResponse {
  results: ICD10Item[]
  total: number
}

export interface ICD10Suggestion {
  icd_kodu: string
  tani: string
  confidence: number
  reasoning: string
  source?: 'tani' | 'semptom' | 'cikarim'
}

export interface ICD10SuggestResponse {
  suggestions: ICD10Suggestion[]
}

export interface ICD10ConfirmedCode {
  icd_kodu: string
  tani: string
  tani_tipi: 'on_tani' | 'kesin_tani'
}
