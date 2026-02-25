import { useAudioLevel } from '../../hooks/useAudioLevel'

function getLevelColor(level: number): string {
  if (level < 0.4) return 'bg-emerald-500'
  if (level < 0.7) return 'bg-yellow-500'
  return 'bg-red-500'
}

export function AudioLevelMeter(): React.JSX.Element {
  const audioLevel = useAudioLevel()
  const color = getLevelColor(audioLevel)
  const widthPercent = Math.max(audioLevel * 100, 2) // minimum 2% for visibility

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-400 w-6 shrink-0">Ses</span>
      <div className="relative h-2.5 w-28 overflow-hidden rounded-full bg-slate-200">
        <div
          className={`absolute inset-y-0 left-0 rounded-full transition-all duration-100 ease-out ${color}`}
          style={{ width: `${widthPercent}%` }}
        />
      </div>
    </div>
  )
}
