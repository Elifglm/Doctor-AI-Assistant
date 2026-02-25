import { useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Info } from 'lucide-react'
import { useRecording } from '../hooks/useRecording'
import { useTranscription } from '../hooks/useTranscription'
import { RecordingControls } from '../components/session/RecordingControls'
import { TranscriptView } from '../components/session/TranscriptView'

export function LiveSessionPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const sessionId = id ? Number(id) : null
  const hasStarted = useRef(false)

  const { startRecording, pauseRecording, resumeRecording, stopRecording, recordingState } =
    useRecording(sessionId)
  const { segments } = useTranscription()

  // Auto-start recording on mount
  useEffect(() => {
    if (sessionId && !hasStarted.current) {
      hasStarted.current = true
      void startRecording()
    }
  }, [sessionId, startRecording])

  const handleStop = (): void => {
    stopRecording()
    if (sessionId) {
      navigate(`/session/${sessionId}/processing`)
    }
  }

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Recording controls - always visible at top */}
      <RecordingControls onPause={pauseRecording} onResume={resumeRecording} onStop={handleStop} />

      {/* Info banner while recording */}
      {(recordingState === 'recording' || recordingState === 'paused') && (
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
