import { User, ChevronRight, Trash2, Loader2 } from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import { useT } from '../../hooks/useT'
import type { Session, VisitType } from '../../types/session'

const visitTypeBadgeColors: Record<VisitType, string> = {
  ilk_muayene: 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
  kontrol: 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200',
  konsultasyon: 'bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300',
  acil: 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300',
}

const visitTypeLabelKeys: Record<VisitType, string> = {
  ilk_muayene: 'card_firstConsult',
  kontrol: 'card_followup',
  konsultasyon: 'card_consultation',
  acil: 'card_emergency',
}

interface SessionCardProps {
  session: Session
  onClick: () => void
  onDelete?: (sessionId: number) => void
  isDeleting?: boolean
}

function formatDateTime(isoString: string): string {
  const date = new Date(isoString)
  const day = date.getDate().toString().padStart(2, '0')
  const month = (date.getMonth() + 1).toString().padStart(2, '0')
  const year = date.getFullYear()
  const hours = date.getHours().toString().padStart(2, '0')
  const minutes = date.getMinutes().toString().padStart(2, '0')
  return `${day}.${month}.${year} ${hours}:${minutes}`
}

export function SessionCard({ session, onClick, onDelete, isDeleting }: SessionCardProps): React.JSX.Element {
  const t = useT()

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      className="flex w-full items-center justify-between rounded-xl bg-white dark:bg-slate-800 p-4 text-left shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60 transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/50 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
    >
      <div className="flex items-center gap-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-700">
          <User className="h-5 w-5 text-slate-500 dark:text-slate-400" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{session.doctor_name}</p>
          {session.patient_name && (
            <p className="text-xs text-slate-500 dark:text-slate-400">{t('card_patient')} {session.patient_name}</p>
          )}
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${visitTypeBadgeColors[session.visit_type]}`}
            >
              {t(visitTypeLabelKeys[session.visit_type])}
            </span>
            <StatusBadge status={session.status} />
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-400 dark:text-slate-500">{formatDateTime(session.created_at)}</span>
        {onDelete && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onDelete(session.id)
            }}
            disabled={isDeleting}
            className="p-1.5 rounded-md text-slate-400 dark:text-slate-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors disabled:opacity-50"
            title={t('card_archiveTooltip')}
          >
            {isDeleting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </button>
        )}
        <ChevronRight className="h-4 w-4 text-slate-400 dark:text-slate-500" />
      </div>
    </div>
  )
}
