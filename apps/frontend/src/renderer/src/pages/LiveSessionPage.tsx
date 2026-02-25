import { useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Info, AlertCircle, RotateCcw } from 'lucide-react'
import { useRecording } from '../hooks/useRecording'
import { useTranscription } from '../hooks/useTranscription'
import { RecordingControls } from '../components/session/RecordingControls'
import { TranscriptView } from '../components/session/TranscriptView'

export function LiveSessionPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const sessionId = id ? Number(id) : null
  const lastStartedId = useRef<number | null>(null)

  const { startRecording, pauseRecording, resumeRecording, stopRecording, recordingState, error } =
    useRecording(sessionId)
  const { segments } = useTranscription()

  // Auto-start recording when sessionId changes (handles both mount and session switch)
  useEffect(() => {
    if (sessionId && lastStartedId.current !== sessionId) {
      lastStartedId.current = sessionId
      startRecording().catch((err) => {
        console.error('Auto-start recording failed:', err)
      })
    }
  }, [sessionId, startRecording])

  const handleStop = (): void => {
    stopRecording()
    if (sessionId) {
      navigate(`/session/${sessionId}/processing`)
    }
  }

  const handleRetry = (): void => {
    startRecording().catch((err) => {
      console.error('Retry recording failed:', err)
    })
  }

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Recording controls - always visible at top */}
      <RecordingControls onPause={pauseRecording} onResume={resumeRecording} onStop={handleStop} />

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-3 rounded-lg bg-red-50 px-4 py-3 ring-1 ring-red-200/60">
          <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800">Kayit baslatılamadı</p>
            <p className="text-sm text-red-600">{error}</p>
          </div>
          <button
            onClick={handleRetry}
            className="flex items-center gap-1.5 rounded-md bg-red-100 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-200 transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Tekrar Dene
          </button>
        </div>
      )}

      {/* Info banner while recording */}
      {!error && (recordingState === 'recording' || recordingState === 'paused') && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 px-4 py-2.5 ring-1 ring-blue-200/60">
          <Info className="h-4 w-4 text-blue-600 shrink-0" />
          <p className="text-sm text-blue-700">
            Kaydi durdurunca isleme baslanacak
          </p>
        </div>
      )}

      {/* Transcript view - scrollable, takes remaining space */}
      <div className="flex-1 overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200/60">
        <TranscriptView segments={segments} />
      </div>
    </div>
  )
}
