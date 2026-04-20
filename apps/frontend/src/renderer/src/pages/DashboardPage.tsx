import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { apiClient } from '../services/apiClient'
import { StatsBar } from '../components/dashboard/StatsBar'
import { SessionCard } from '../components/dashboard/SessionCard'
import { useSessionList } from '../hooks/useSession'
import type { Session, SessionStatus } from '../types/session'

function getSessionRoute(session: Session): string {
  const routes: Record<SessionStatus, string> = {
    NOT_STARTED: `/session/${session.id}/live`,
    RECORDING: `/session/${session.id}/live`,
    PROCESSING: `/session/${session.id}/processing`,
    AWAITING_REVIEW: `/session/${session.id}/review`,
    COMPLETED: `/session/${session.id}/review`,
    ARCHIVED: `/session/${session.id}/review`,
  }
  return routes[session.status]
}

export function DashboardPage(): React.JSX.Element {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const handleDelete = useCallback(async (sessionId: number) => {
    if (!confirm('Bu görüşmeyi arşivlemek istediğinizden emin misiniz?')) return
    setDeletingId(sessionId)
    try {
      await apiClient.delete(`/api/v1/sessions/${sessionId}`)
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    } catch (err) {
      console.error('Silme hatasi:', err)
      alert('Görüşme silinemedi')
    } finally {
      setDeletingId(null)
    }
  }, [queryClient])

  const { data, isLoading, error } = useSessionList({
    limit: 10,
    sort: 'created_at:desc',
  })

  const sessions = data?.items ?? []

  const today = new Date()
  const todayStr = `${today.getFullYear()}-${(today.getMonth() + 1).toString().padStart(2, '0')}-${today.getDate().toString().padStart(2, '0')}`

  const todayCount = sessions.filter((s) => s.created_at.startsWith(todayStr)).length
  const pendingCount = sessions.filter((s) => s.status === 'AWAITING_REVIEW').length
  const completedCount = sessions.filter((s) => s.status === 'COMPLETED').length

  // Fetch today's appointment count from OpenEMR
  const [appointmentCount, setAppointmentCount] = useState(0)
  useEffect(() => {
    apiClient
      .get<{ total: number }>(`/api/v1/appointments?appointment_date=${todayStr}`)
      .then((res) => setAppointmentCount(res.total))
      .catch(() => setAppointmentCount(0))
  }, [todayStr])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Ana Sayfa</h1>
        <p className="text-sm text-slate-500 mt-1">Gorusme yonetimi ve genel bakis</p>
      </div>

      <StatsBar
        todayCount={todayCount}
        pendingCount={pendingCount}
        completedCount={completedCount}
        appointmentCount={appointmentCount}
      />

      <div>
        <h2 className="mb-3 text-lg font-semibold text-slate-800">Son Görüşmeler</h2>

        {isLoading && (
          <div className="flex items-center justify-center rounded-xl bg-white p-12 shadow-sm ring-1 ring-slate-200/60">
            <div className="flex flex-col items-center gap-2">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
              <p className="text-sm text-slate-500">Görüşmeler yükleniyor...</p>
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-3 rounded-xl bg-red-50 p-4 ring-1 ring-red-200">
            <AlertCircle className="h-5 w-5 text-red-500 shrink-0" />
            <p className="text-sm text-red-700">
              Görüşmeler yüklenirken hata oluştu: {error instanceof Error ? error.message : 'Bilinmeyen hata'}
            </p>
          </div>
        )}

        {!isLoading && !error && sessions.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl bg-white p-12 shadow-sm ring-1 ring-slate-200/60">
            <p className="text-sm text-slate-500">Henuz gorusme bulunmuyor</p>
            <button
              onClick={() => navigate('/calendar')}
              className="mt-3 text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Randevularinizi gorun
            </button>
          </div>
        )}

        {!isLoading && !error && sessions.length > 0 && (
          <div className="space-y-2">
            {sessions.map((session) => (
              <SessionCard
                key={session.id}
                session={session}
                onClick={() => navigate(getSessionRoute(session))}
                onDelete={handleDelete}
                isDeleting={deletingId === session.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
