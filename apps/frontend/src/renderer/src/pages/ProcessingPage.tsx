import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useTranscription } from '../hooks/useTranscription'

const stageLabels: Record<string, string> = {
  validating: 'Dosya dogrulaniyor...',
  noise_suppression: 'Gurultu bastirma...',
  transcription: 'Transkripsiyon...',
  diarization: 'Konusmaci ayristirma...',
  saving: 'Sonuclar kaydediliyor...',
}

function getStageIndex(stage: string): number {
  const stageOrder = ['validating', 'noise_suppression', 'transcription', 'diarization', 'saving']
  const idx = stageOrder.indexOf(stage)
  return idx >= 0 ? idx : 0
}

function getStageLabel(stage: string): string {
  return stageLabels[stage] || stage || 'Hazirlaniyor...'
}

export function ProcessingPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const sessionId = id ? Number(id) : null

  const { processingStage, processingMessage, processingProgress, hasResults } = useTranscription()

  // Navigate to review page when processing is complete
  useEffect(() => {
    if (processingProgress >= 1.0 && hasResults && sessionId) {
      const timeout = setTimeout(() => {
        navigate(`/session/${sessionId}/review`)
      }, 500) // Small delay for UX
      return (): void => {
        clearTimeout(timeout)
      }
    }
    return undefined
  }, [processingProgress, hasResults, sessionId, navigate])

  const stageIndex = getStageIndex(processingStage)
  const totalStages = 5
  const stageProgressPercent = Math.round((stageIndex / (totalStages - 1)) * 100)
  // Use the finer progress from server if available, otherwise use stage-based progress
  const displayProgress =
    processingProgress > 0 ? Math.round(processingProgress * 100) : stageProgressPercent

  return (
    <div className="flex h-full items-center justify-center">
      <div className="w-full max-w-md space-y-8 text-center">
        {/* Spinner */}
        <div className="flex justify-center">
          <div className="relative">
            <Loader2 className="h-16 w-16 animate-spin text-blue-600" />
          </div>
        </div>

        {/* Stage title */}
        <div className="space-y-2">
          <h2 className="text-xl font-bold text-slate-800">Isleniyor</h2>
          <p className="text-base font-medium text-slate-600">{getStageLabel(processingStage)}</p>
        </div>

        {/* Stage indicators */}
        <div className="flex items-center justify-center gap-1">
          {Array.from({ length: totalStages }).map((_, i) => (
            <div
              key={i}
              className={`h-2 w-12 rounded-full transition-colors duration-300 ${
                i <= stageIndex ? 'bg-blue-600' : 'bg-slate-200'
              }`}
            />
          ))}
        </div>
        <p className="text-xs text-slate-400">
          Asama {Math.min(stageIndex + 1, totalStages)}/{totalStages}
        </p>

        {/* Progress bar */}
        <div className="space-y-2">
          <div className="relative h-3 w-full overflow-hidden rounded-full bg-slate-200">
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-blue-600 transition-all duration-500 ease-out"
              style={{ width: `${displayProgress}%` }}
            />
          </div>
          <p className="text-sm font-medium text-slate-500">%{displayProgress}</p>
        </div>

        {/* Processing message */}
        {processingMessage && (
          <p className="text-sm text-slate-400">{processingMessage}</p>
        )}
      </div>
    </div>
  )
}
