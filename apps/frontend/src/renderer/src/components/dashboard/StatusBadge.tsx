import { cn } from '../../lib/utils'
import type { SessionStatus } from '../../types/session'

const statusConfig: Record<SessionStatus, { label: string; className: string }> = {
  NOT_STARTED: {
    label: 'Başlamadı',
    className: 'bg-slate-100 text-slate-700 ring-slate-200',
  },
  RECORDING: {
    label: 'Kayıt Yapılıyor',
    className: 'bg-red-50 text-red-700 ring-red-200',
  },
  PROCESSING: {
    label: 'İşleniyor',
    className: 'bg-amber-50 text-amber-700 ring-amber-200',
  },
  AWAITING_REVIEW: {
    label: 'İnceleme Bekliyor',
    className: 'bg-yellow-50 text-yellow-700 ring-yellow-200',
  },
  COMPLETED: {
    label: 'Tamamlandı',
    className: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  },
  ARCHIVED: {
    label: 'Arşivlendi',
    className: 'bg-gray-100 text-gray-600 ring-gray-200',
  },
}

interface StatusBadgeProps {
  status: SessionStatus
}

export function StatusBadge({ status }: StatusBadgeProps): React.JSX.Element {
  const config = statusConfig[status]

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset',
        config.className
      )}
    >
      {config.label}
    </span>
  )
}
