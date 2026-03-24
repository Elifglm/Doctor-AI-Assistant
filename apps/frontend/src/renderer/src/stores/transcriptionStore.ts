import { create } from 'zustand'
import type { TranscriptionSegment } from '../types/transcription'

interface TranscriptionState {
  segments: TranscriptionSegment[]
  processingStage: string
  processingMessage: string
  processingProgress: number
  /** Report ID set when the backend sends "report_ready" via WebSocket. */
  autoReportId: number | null
  /** True once the auto-report flow has completed (success or warning/skip). */
  reportFlowDone: boolean
  setSegments: (segments: TranscriptionSegment[]) => void
  addSegment: (segment: TranscriptionSegment) => void
  updateSegment: (id: number, updates: Partial<TranscriptionSegment>) => void
  setProcessing: (stage: string, message: string, progress?: number) => void
  setAutoReportReady: (reportId: number) => void
  setReportFlowDone: () => void
  clearSegments: () => void
  reset: () => void
}

export const useTranscriptionStore = create<TranscriptionState>()((set) => ({
  segments: [],
  processingStage: '',
  processingMessage: '',
  processingProgress: 0,
  autoReportId: null,
  reportFlowDone: false,
  setSegments: (segments) => set({ segments }),
  addSegment: (segment) => set((s) => ({ segments: [...s.segments, segment] })),
  updateSegment: (id, updates) =>
    set((s) => ({
      segments: s.segments.map((seg) => (seg.id === id ? { ...seg, ...updates } : seg)),
    })),
  setProcessing: (stage, message, progress = 0) =>
    set({ processingStage: stage, processingMessage: message, processingProgress: progress }),
  setAutoReportReady: (reportId) => set({ autoReportId: reportId, reportFlowDone: true }),
  setReportFlowDone: () => set({ reportFlowDone: true }),
  clearSegments: () => set({ segments: [] }),
  reset: () =>
    set({
      segments: [],
      processingStage: '',
      processingMessage: '',
      processingProgress: 0,
      autoReportId: null,
      reportFlowDone: false,
    }),
}))
