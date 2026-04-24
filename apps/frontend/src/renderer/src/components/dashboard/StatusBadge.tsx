import { cn } from '../../lib/utils'
import { useT } from '../../hooks/useT'
import type { SessionStatus } from '../../types/session'

const statusClassMap: Record<SessionStatus, string> = {
  NOT_STARTED: 'bg-slate-100 text-slate-700 ring-slate-200',
  RECORDING: 'bg-red-50 text-red-700 ring-red-200',
  PROCESSING: 'bg-amber-50 text-amber-700 ring-amber-200',
  AWAITING_REVIEW: 'bg-yellow-50 text-yellow-700 ring-yellow-200',
  COMPLETED: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  ARCHIVED: 'bg-gray-100 text-gray-600 ring-gray-200',
}

const statusKeyMap: Record<SessionStatus, string> = {
  NOT_STARTED: 'status_notStarted',
  RECORDING: 'status_recording',
  PROCESSING: 'status_processing',
  AWAITING_REVIEW: 'status_awaitingReview',
  COMPLETED: 'status_completed',
  ARCHIVED: 'status_archived',
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
