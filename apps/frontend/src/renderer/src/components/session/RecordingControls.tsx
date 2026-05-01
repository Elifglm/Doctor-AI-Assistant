import { Pause, Play, Square } from 'lucide-react'
import { useSessionStore } from '../../stores/sessionStore'
import { useT } from '../../hooks/useT'
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
  const t = useT()

  return (
    <div className="flex items-center justify-between rounded-xl bg-white dark:bg-slate-800 px-5 py-3.5 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60">
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
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            {isRecording ? t('rec_recording') : isPaused ? t('rec_paused') : t('rec_waiting')}
          </span>
        </div>
        <span className="font-mono text-lg font-semibold text-slate-800 dark:text-slate-100 tabular-nums">
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
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors hover:bg-slate-200 dark:hover:bg-slate-600 "
            title={t('rec_pause')}
          >
            <Pause className="h-4 w-4" />
          </button>
        ) : isPaused ? (
          <button
            onClick={onResume}
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 transition-colors hover:bg-blue-100"
            title={t('rec_resume')}
          >
            <Play className="h-4 w-4" />
          </button>
        ) : null}
        <button
          onClick={onStop}
          disabled={recordingState === 'idle'}
          className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-50 dark:bg-red-900/30 text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
          title={t('rec_stop')}
        >
          <Square className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
