import { create } from 'zustand'
import type { TranscriptionSegment } from '../types/transcription'

interface TranscriptionState {
  segments: TranscriptionSegment[]
  processingStage: string
  processingMessage: string
  processingProgress: number
  setSegments: (segments: TranscriptionSegment[]) => void
  addSegment: (segment: TranscriptionSegment) => void
  updateSegment: (id: number, updates: Partial<TranscriptionSegment>) => void
  setProcessing: (stage: string, message: string, progress?: number) => void
  clearSegments: () => void
  reset: () => void
}

export const useTranscriptionStore = create<TranscriptionState>()((set) => ({
  segments: [],
  processingStage: '',
  processingMessage: '',
  processingProgress: 0,
  setSegments: (segments) => set({ segments }),
  addSegment: (segment) => set((s) => ({ segments: [...s.segments, segment] })),
  updateSegment: (id, updates) =>
    set((s) => ({
      segments: s.segments.map((seg) => (seg.id === id ? { ...seg, ...updates } : seg)),
    })),
  setProcessing: (stage, message, progress = 0) =>
    set({ processingStage: stage, processingMessage: message, processingProgress: progress }),
  clearSegments: () => set({ segments: [] }),
  reset: () =>
    set({ segments: [], processingStage: '', processingMessage: '', processingProgress: 0 }),
}))
