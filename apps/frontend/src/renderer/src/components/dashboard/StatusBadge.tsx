import { cn } from '../../lib/utils'
import { useT } from '../../hooks/useT'
import type { SessionStatus } from '../../types/session'

const statusClassMap: Record<SessionStatus, string> = {
  NOT_STARTED: 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 ring-slate-200',
  RECORDING: 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 ring-red-200 dark:ring-red-800',
  PROCESSING: 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 ring-amber-200 dark:ring-amber-800',
  AWAITING_REVIEW: 'bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 ring-yellow-200',
  COMPLETED: 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 ring-emerald-200 dark:ring-emerald-800',
}

const statusKeyMap: Record<SessionStatus, string> = {
  NOT_STARTED: 'status_notStarted',
  RECORDING: 'status_recording',
  PROCESSING: 'status_processing',
  AWAITING_REVIEW: 'status_awaitingReview',
  COMPLETED: 'status_completed',
}

interface StatusBadgeProps {
  status: SessionStatus
}

export function StatusBadge({ status }: StatusBadgeProps): React.JSX.Element {
  const t = useT()

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset',
        statusClassMap[status]
      )}
    >
      {t(statusKeyMap[status])}
    </span>
  )
}
