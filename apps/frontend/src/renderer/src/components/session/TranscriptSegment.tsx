import { User, Stethoscope } from 'lucide-react'
import { SpeakerLabel } from './SpeakerLabel'
import { useT } from '../../hooks/useT'
import type { TranscriptionSegment } from '../../types/transcription'

interface TranscriptSegmentProps {
  segment: TranscriptionSegment
  index: number
}

function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

function isDoctor(speaker: string): boolean {
  return (
    speaker.toLowerCase().includes('doctor') || speaker.toLowerCase().includes('doktor')
  )
}

export function TranscriptSegmentItem({
  segment,
  index,
}: TranscriptSegmentProps): React.JSX.Element {
  const t = useT()
  const doctor = isDoctor(segment.speaker)
  const borderColor = doctor ? 'border-l-blue-600' : 'border-l-emerald-600'
  const bgColor = index % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-slate-50 dark:bg-slate-900'
  const IconComponent = doctor ? Stethoscope : User
  const iconColor = doctor ? 'text-blue-600' : 'text-emerald-600'
  const displayLabel =
    segment.speaker_label || (doctor ? t('speaker_doctor_short') : t('speaker_patient_short'))

  return (
    <div className={`border-l-[3px] ${borderColor} ${bgColor} px-4 py-3`}>
      <div className="flex items-center gap-2 mb-1.5">
        <IconComponent className={`h-4 w-4 ${iconColor} shrink-0`} />
        <SpeakerLabel speaker={segment.speaker} speakerLabel={displayLabel} />
        <span className="font-mono text-xs text-slate-400 dark:text-slate-500 ml-auto">
          {formatTimestamp(segment.start_time)} - {formatTimestamp(segment.end_time)}
        </span>
      </div>
      <p className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed pl-6">{segment.text}</p>
    </div>
  )
}
