import { Pause, Play, Square } from 'lucide-react'
import { useSessionStore } from '../../stores/sessionStore'
import { AudioLevelMeter } from './AudioLevelMeter'

interface RecordingControlsProps {
  onPause: () => void
  onResume: () => void
  onStop: () => void
}

function formatTime(totalSeconds: number): string {
  const mins = Math.floor(totalSeconds / 60)
  const secs = totalSeconds % 60
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

export function RecordingControls({
  onPause,
  onResume,
  onStop,
}: RecordingControlsProps): React.JSX.Element {
  const recordingState = useSessionStore((s) => s.recordingState)
  const elapsedTime = useSessionStore((s) => s.elapsedTime)
  const isRecording = recordingState === 'recording'
  const isPaused = recordingState === 'paused'

  return (
    <div className="flex items-center justify-between rounded-xl bg-white px-5 py-3.5 shadow-sm ring-1 ring-slate-200/60">
      {/* Left: Recording indicator and timer */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block h-3 w-3 rounded-full ${
              isRecording
                ? 'animate-pulse bg-red-500'
                : isPaused
                  ? 'bg-yellow-500'
                  : 'bg-slate-300'
            }`}
          />
          <span className="text-sm font-medium text-slate-700">
            {isRecording ? 'Kayıt yapılıyor' : isPaused ? 'Duraklatıldı' : 'Bekleniyor'}
          </span>
        </div>
        <span className="font-mono text-lg font-semibold text-slate-800 tabular-nums">
          {formatTime(elapsedTime)}
        </span>
      </div>

      {/* Center: Audio level meter */}
      <AudioLevelMeter />

      {/* Right: Control buttons */}
      <div className="flex items-center gap-2">
        {isRecording ? (
          <button
            onClick={onPause}
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-700 transition-colors hover:bg-slate-200"
            title="Duraklat"
          >
            <Pause className="h-4 w-4" />
          </button>
        ) : isPaused ? (
          <button
            onClick={onResume}
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-700 transition-colors hover:bg-blue-100"
            title="Devam et"
          >
            <Play className="h-4 w-4" />
          </button>
        ) : null}
        <button
          onClick={onStop}
          disabled={recordingState === 'idle'}
          className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-50 text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
          title="Kaydı durdur"
        >
          <Square className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
