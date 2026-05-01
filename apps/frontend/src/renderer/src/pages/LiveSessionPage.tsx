import { useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Info, AlertCircle, RotateCcw, Loader2 } from 'lucide-react'
import { useRecording } from '../hooks/useRecording'
import { useTranscription } from '../hooks/useTranscription'
import { useSessionStore } from '../stores/sessionStore'
import { useT } from '../hooks/useT'
import { RecordingControls } from '../components/session/RecordingControls'

const stageLabelKeys: Record<string, string> = {
  'Stage 0/4': 'live_validating',
  'Stage 1/4': 'live_transcribing',
  'Stage 2/4': 'live_correcting',
  'Stage 3/4': 'live_diarizing',
  'Stage 4/4': 'live_generating',
}

function getStageInfo(stage: string): { index: number; total: number } {
  const match = stage.match(/Stage (\d+)\/(\d+)/)
  if (match) {
    return { index: parseInt(match[1], 10), total: parseInt(match[2], 10) + 1 }
  }
  return { index: 0, total: 7 }
}

export function LiveSessionPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const sessionId = id ? Number(id) : null
  const lastStartedId = useRef<number | null>(null)
  const t = useT()

  const { startRecording, pauseRecording, resumeRecording, stopRecording, recordingState, error } =
    useRecording(sessionId)
  const { processingStage, processingMessage, processingProgress, hasResults, reportFlowDone } =
    useTranscription()
  const recordingStateFromStore = useSessionStore((s) => s.recordingState)

  // Auto-start recording when sessionId changes (handles React StrictMode)
  useEffect(() => {
    if (sessionId && lastStartedId.current !== sessionId) {
      lastStartedId.current = sessionId
      startRecording().catch((err) => {
        console.error('Auto-start recording failed:', err)
      })
    }
    return () => {
      lastStartedId.current = null
    }
  }, [sessionId, startRecording])

  // Navigate to review when results are ready AND report flow is done
  useEffect(() => {
    if (hasResults && reportFlowDone && sessionId && recordingStateFromStore === 'idle') {
      const timeout = setTimeout(() => {
        navigate(`/session/${sessionId}/review`)
      }, 500)
      return (): void => {
        clearTimeout(timeout)
      }
    }
    return undefined
  }, [hasResults, reportFlowDone, sessionId, recordingStateFromStore, navigate])

  const handleStop = (): void => {
    stopRecording()
  }

  const handleRetry = (): void => {
    startRecording().catch((err) => {
      console.error('Retry recording failed:', err)
    })
  }

  const isProcessing = recordingStateFromStore === 'processing'
  const { index: stageIndex, total: totalStages } = getStageInfo(processingStage)
  const displayProgress = Math.min(
    processingProgress > 0 ? Math.round(processingProgress * 100) : Math.round((stageIndex / Math.max(totalStages - 1, 1)) * 100),
    100
  )

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Recording controls - visible when recording */}
      {!isProcessing && (
        <RecordingControls onPause={pauseRecording} onResume={resumeRecording} onStop={handleStop} />
      )}

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-3 rounded-lg bg-red-50 dark:bg-red-900/30 px-4 py-3 ring-1 ring-red-200/60">
          <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800 dark:text-red-200">{t('live_startFailed')}</p>
            <p className="text-sm text-red-600">{error}</p>
          </div>
          <button
            onClick={handleRetry}
            className="flex items-center gap-1.5 rounded-md bg-red-100 px-3 py-1.5 text-sm font-medium text-red-700 dark:text-red-300 hover:bg-red-200 transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            {t('live_retry')}
          </button>
        </div>
      )}

      {/* Info banner while recording */}
      {!error && !isProcessing && (recordingState === 'recording' || recordingState === 'paused') && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 dark:bg-blue-900/30 px-4 py-2.5 ring-1 ring-blue-200/60">
          <Info className="h-4 w-4 text-blue-600 shrink-0" />
          <p className="text-sm text-blue-700 dark:text-blue-300">{t('live_recordingInProgress')}</p>
        </div>
      )}

      {/* Processing overlay */}
      {isProcessing && (
        <div className="flex flex-col items-center justify-center gap-6 py-12">
          <Loader2 className="h-12 w-12 animate-spin text-blue-600" />
          <div className="text-center space-y-1">
            <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">{t('live_processing')}</h2>
            <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
              {stageLabelKeys[processingStage] ? t(stageLabelKeys[processingStage]) : processingMessage || t('live_preparing')}
            </p>
          </div>

          {/* Stage indicators */}
          <div className="flex items-center gap-1">
            {Array.from({ length: totalStages }).map((_, i) => (
              <div
                key={i}
                className={`h-2 w-10 rounded-full transition-colors duration-300 ${
                  i <= stageIndex ? 'bg-blue-600' : 'bg-slate-200 dark:bg-slate-700'
                }`}
              />
            ))}
          </div>
          <p className="text-xs text-slate-400 dark:text-slate-500">
            {t('live_stage', { index: Math.min(stageIndex + 1, totalStages), total: totalStages })}
          </p>

          {/* Progress bar */}
          <div className="w-full max-w-sm space-y-2">
            <div className="relative h-3 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-blue-600 transition-all duration-500 ease-out"
                style={{ width: `${displayProgress}%` }}
              />
            </div>
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400 text-center">%{displayProgress}</p>
          </div>
        </div>
      )}

      {/* Recording placeholder - no transcript during recording in batch mode */}
    </div>
  )
}
