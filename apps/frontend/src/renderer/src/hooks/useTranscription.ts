import { useTranscriptionStore } from '../stores/transcriptionStore'

export function useTranscription() {
  const {
    segments,
    processingStage,
    processingMessage,
    processingProgress,
    autoReportId,
    reportFlowDone,
  } = useTranscriptionStore()

  return {
    segments,
    processingStage,
    processingMessage,
    processingProgress,
    autoReportId,
    reportFlowDone,
    hasResults: segments.length > 0,
  }
}
