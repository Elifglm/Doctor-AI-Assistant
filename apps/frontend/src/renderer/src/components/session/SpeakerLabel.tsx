interface SpeakerLabelProps {
  speaker: string
  speakerLabel: string
}

function getSpeakerColor(speaker: string): { bg: string; text: string; border: string } {
  // Doctor-type speakers
  if (speaker.toLowerCase().includes('doctor') || speaker.toLowerCase().includes('doktor')) {
    return {
      bg: 'bg-blue-50',
      text: 'text-blue-700',
      border: 'border-blue-200',
    }
  }
  // Patient-type speakers
  if (speaker.toLowerCase().includes('patient') || speaker.toLowerCase().includes('hasta')) {
    return {
      bg: 'bg-emerald-50',
      text: 'text-emerald-700',
      border: 'border-emerald-200',
    }
  }
  // Default / unknown speakers
  return {
    bg: 'bg-slate-50',
    text: 'text-slate-700',
    border: 'border-slate-200',
  }
}

export function SpeakerLabel({ speaker, speakerLabel }: SpeakerLabelProps): React.JSX.Element {
  const colors = getSpeakerColor(speaker)

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${colors.bg} ${colors.text} ${colors.border}`}
    >
      {speakerLabel}
    </span>
  )
}
