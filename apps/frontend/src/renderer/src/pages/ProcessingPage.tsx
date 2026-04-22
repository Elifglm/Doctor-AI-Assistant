import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Loader2, ShieldCheck } from 'lucide-react'
import { useTranscription } from '../hooks/useTranscription'
import { useT } from '../hooks/useT'

// TODO: Replace hardcoded value with a real backend endpoint once
// GET /api/v1/settings/deid is implemented (returns { deid_enabled: boolean }).
const DEID_ENABLED = true

const stageLabelKeys: Record<string, string> = {
  'Stage 0/4': 'live_validating',
  'Stage 1/4': 'live_noiseReduction',
  'Stage 2/4': 'live_transcribing',
  'Stage 3/4': 'live_diarizing',
  'Stage 4/4': 'live_generating',
}

function getStageIndex(stage: string): number {
  const stages = ['Stage 0/4', 'Stage 1/4', 'Stage 2/4', 'Stage 3/4', 'Stage 4/4']
  const idx = stages.indexOf(stage)
  return idx >= 0 ? idx : 0
}

export function ProcessingPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const sessionId = id ? Number(id) : null
  const t = useT()

  const { processingStage, processingMessage, processingProgress, hasResults, reportFlowDone } = useTranscription()

  // Navigate to review page when processing is complete and report flow is done
  useEffect(() => {
    if (processingProgress >= 1.0 && hasResults && reportFlowDone && sessionId) {
      const timeout = setTimeout(() => {
        navigate(`/session/${sessionId}/review`)
      }, 500)
      return (): void => {
        clearTimeout(timeout)
      }
    }
    return undefined
  }, [processingProgress, hasResults, reportFlowDone, sessionId, navigate])

  const stageIndex = getStageIndex(processingStage)
  const totalStages = 5
  const displayProgress =
    processingProgress > 0 ? Math.round(processingProgress * 100) : Math.round((stageIndex / (totalStages - 1)) * 100)

  return (
    <div className="flex h-full items-center justify-center">
      <div className="w-full max-w-md space-y-8 text-center">
        <div className="flex justify-center">
          <Loader2 className="h-16 w-16 animate-spin text-blue-600" />
        </div>

        <div className="space-y-2">
          <h2 className="text-xl font-bold text-slate-800">{t('live_processing')}</h2>
          <p className="text-base font-medium text-slate-600">
            {stageLabelKeys[processingStage] ? t(stageLabelKeys[processingStage]) : processingMessage || t('live_preparing')}
          </p>
        </div>

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
          {t('live_stage', { index: Math.min(stageIndex + 1, totalStages), total: totalStages })}
        </p>

        <div className="space-y-2">
          <div className="relative h-3 w-full overflow-hidden rounded-full bg-slate-200">
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-blue-600 transition-all duration-500 ease-out"
              style={{ width: `${displayProgress}%` }}
            />
          </div>
          <p className="text-sm font-medium text-slate-500">%{displayProgress}</p>
        </div>

        {processingMessage && (
          <p className="text-sm text-slate-400">{processingMessage}</p>
        )}

        {DEID_ENABLED && (
          <div className="flex justify-center">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
              {t('live_piiActive')}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
