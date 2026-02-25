import { useTranscriptionStore } from '../stores/transcriptionStore'

export function useTranscription() {
  const { segments, processingStage, processingMessage, processingProgress } =
    useTranscriptionStore()

  return {
    segments,
    processingStage,
    processingMessage,
    processingProgress,
    hasResults: segments.length > 0,
  }
}
