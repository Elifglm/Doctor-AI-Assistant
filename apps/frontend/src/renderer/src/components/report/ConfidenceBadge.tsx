import { cn } from '../../lib/utils'
import type { ReportConfidence } from '../../types/report'

const confidenceConfig: Record<ReportConfidence, { label: string; className: string }> = {
  high: {
    label: 'Yuksek',
    className: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  },
  medium: {
    label: 'Orta',
    className: 'bg-amber-50 text-amber-700 ring-amber-200',
  },
  low: {
    label: 'Dusuk',
    className: 'bg-gray-100 text-gray-600 ring-gray-200',
  },
}

interface ConfidenceBadgeProps {
  confidence: ReportConfidence
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps): React.JSX.Element {
  const config = confidenceConfig[confidence]

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        config.className
      )}
    >
      {config.label}
    </span>
  )
}
