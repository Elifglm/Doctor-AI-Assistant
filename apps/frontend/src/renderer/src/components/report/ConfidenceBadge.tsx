import { cn } from '../../lib/utils'
import { useT } from '../../hooks/useT'
import type { ReportConfidence } from '../../types/report'

const confidenceConfig: Record<ReportConfidence, { labelKey: string; className: string }> = {
  high: {
    labelKey: 'confidence_high',
    className: 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 ring-emerald-200 dark:ring-emerald-800',
  },
  medium: {
    labelKey: 'confidence_medium',
    className: 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 ring-amber-200 dark:ring-amber-800',
  },
  low: {
    labelKey: 'confidence_low',
    className: 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-300 ring-gray-200',
  },
}

interface ConfidenceBadgeProps {
  confidence: ReportConfidence
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps): React.JSX.Element {
  const config = confidenceConfig[confidence]
  const t = useT()

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        config.className
      )}
    >
      {t(config.labelKey)}
    </span>
  )
}
