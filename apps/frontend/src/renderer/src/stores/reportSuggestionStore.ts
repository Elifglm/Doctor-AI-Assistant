import { create } from 'zustand'
import type { ICD10Suggestion } from '../types/icd10'
import type { SUTSuggestion } from '../types/sut_tetkik'

/**
 * AI önerileri (ICD-10 ve SUT tetkik) session id'sine göre önbellekte tutulur.
 *
 * ReportReviewPage "geri" ile unmount olunca ICD10Selector / SutTetkikSelector
 * bileşenlerinin local state'i silinir. Bu store, uygulama açık olduğu sürece
 * önerileri koruyarak sayfaya geri dönüldüğünde tekrar gösterilmelerini sağlar.
 *
 * Bellek-içidir — uygulama tamamen kapatılınca temizlenir; öneriler "AI Öner"
 * ile yeniden üretilebilir.
 */
interface ReportSuggestionState {
  icd: Record<number, ICD10Suggestion[]>
  sut: Record<number, SUTSuggestion[]>
  setIcd: (sessionId: number, suggestions: ICD10Suggestion[]) => void
  setSut: (sessionId: number, suggestions: SUTSuggestion[]) => void
}

export const useReportSuggestionStore = create<ReportSuggestionState>((set) => ({
  icd: {},
  sut: {},
  setIcd: (sessionId, suggestions) =>
    set((s) => ({ icd: { ...s.icd, [sessionId]: suggestions } })),
  setSut: (sessionId, suggestions) =>
    set((s) => ({ sut: { ...s.sut, [sessionId]: suggestions } })),
}))
