import { User, ChevronRight } from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import type { Session, VisitType } from '../../types/session'

const visitTypeLabels: Record<VisitType, string> = {
  ilk_muayene: 'İlk Muayene',
  kontrol: 'Kontrol',
  konsultasyon: 'Konsültasyon',
  acil: 'Acil',
}

const visitTypeBadgeColors: Record<VisitType, string> = {
  ilk_muayene: 'bg-blue-50 text-blue-700',
  kontrol: 'bg-slate-100 text-slate-700',
  konsultasyon: 'bg-purple-50 text-purple-700',
  acil: 'bg-red-50 text-red-700',
}

interface SessionCardProps {
  session: Session
  onClick: () => void
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

export function SessionCard({ session, onClick }: SessionCardProps): React.JSX.Element {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center justify-between rounded-xl bg-white p-4 text-left shadow-sm ring-1 ring-slate-200/60 transition-colors hover:bg-slate-50"
    >
      <div className="flex items-center gap-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100">
          <User className="h-5 w-5 text-slate-500" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-slate-800">{session.doctor_name}</p>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${visitTypeBadgeColors[session.visit_type]}`}
            >
              {visitTypeLabels[session.visit_type]}
            </span>
            <StatusBadge status={session.status} />
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-400">{formatDateTime(session.created_at)}</span>
        <ChevronRight className="h-4 w-4 text-slate-400" />
      </div>
    </button>
  )
}
