import { create } from 'zustand'

type RecordingState = 'idle' | 'recording' | 'paused' | 'processing'

interface SessionState {
  currentSessionId: number | null
  recordingState: RecordingState
  elapsedTime: number
  audioLevel: number
  setCurrentSession: (id: number | null) => void
  setRecordingState: (state: RecordingState) => void
  setElapsedTime: (time: number) => void
  setAudioLevel: (level: number) => void
  reset: () => void
}

export const useSessionStore = create<SessionState>()((set) => ({
  currentSessionId: null,
  recordingState: 'idle',
  elapsedTime: 0,
  audioLevel: 0,
  setCurrentSession: (id) => set({ currentSessionId: id }),
  setRecordingState: (recordingState) => set({ recordingState }),
  setElapsedTime: (elapsedTime) => set({ elapsedTime }),
  setAudioLevel: (audioLevel) => set({ audioLevel }),
  reset: () =>
    set({ currentSessionId: null, recordingState: 'idle', elapsedTime: 0, audioLevel: 0 }),
}))
