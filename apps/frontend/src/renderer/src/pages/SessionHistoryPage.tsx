import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Loader2,
  Calendar,
  Filter,
  Trash2,
} from 'lucide-react'
import { apiClient } from '../services/apiClient'
import { StatusBadge } from '../components/dashboard/StatusBadge'
import type { Session, SessionListResponse, SessionStatus, VisitType } from '../types/session'

const statusFilterOptions: { value: string; label: string }[] = [
  { value: '', label: 'Tümü' },
  { value: 'AWAITING_REVIEW', label: 'Bekleyen' },
  { value: 'COMPLETED', label: 'Tamamlanan' },
  { value: 'ARCHIVED', label: 'Arşivlenen' },
]

const visitTypeLabels: Record<VisitType, string> = {
  ilk_muayene: 'İlk Muayene',
  kontrol: 'Kontrol',
  konsultasyon: 'Konsültasyon',
  acil: 'Acil',
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

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '-'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}dk ${secs}sn`
}

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

export function SessionHistoryPage(): React.JSX.Element {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const handleDelete = useCallback(async (e: React.MouseEvent, sessionId: number) => {
    e.stopPropagation() // Satir tiklamasini engelle
    if (!confirm('Bu görüşmeyi arşivlemek istediğinizden emin misiniz?')) return
    setDeletingId(sessionId)
    try {
      await apiClient.delete(`/api/v1/sessions/${sessionId}`)
      queryClient.invalidateQueries({ queryKey: ['sessions-history'] })
    } catch (err) {
      console.error('Silme hatasi:', err)
      alert('Görüşme silinemedi')
    } finally {
      setDeletingId(null)
    }
  }, [queryClient])

  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [page, setPage] = useState(1)
  const limit = 15

  const searchParams = new URLSearchParams()
  searchParams.set('page', page.toString())
  searchParams.set('limit', limit.toString())
  searchParams.set('sort', 'created_at:desc')
  if (statusFilter) searchParams.set('status', statusFilter)
  if (search) searchParams.set('search', search)
  if (fromDate) searchParams.set('from_date', fromDate)
  if (toDate) searchParams.set('to_date', toDate)

  const queryString = searchParams.toString()

  const { data, isLoading, error } = useQuery<SessionListResponse>({
    queryKey: ['sessions-history', statusFilter, search, fromDate, toDate, page],
    queryFn: () =>
      apiClient.get<SessionListResponse>(`/api/v1/sessions?${queryString}`),
  })

  const sessions = data?.items ?? []
  const totalPages = data?.pages ?? 1

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Görüşme Geçmişi</h1>
        <p className="text-sm text-slate-500 mt-1">Tüm görüşmeleri görüntüleyip yönetin</p>
      </div>

      {/* Filter bar */}
      <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200/60">
        <div className="flex flex-wrap items-end gap-4">
          {/* Status filter */}
          <div className="flex-shrink-0">
            <label
              htmlFor="statusFilter"
              className="mb-1.5 block text-xs font-medium text-slate-600"
            >
              <Filter className="inline h-3.5 w-3.5 mr-1" />
              Durum
            </label>
            <select
              id="statusFilter"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                setPage(1)
              }}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              {statusFilterOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Search */}
          <div className="flex-1 min-w-[200px]">
            <label
              htmlFor="searchInput"
              className="mb-1.5 block text-xs font-medium text-slate-600"
            >
              <Search className="inline h-3.5 w-3.5 mr-1" />
              Arama
            </label>
            <input
              id="searchInput"
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              placeholder="Doktor adı veya hasta ID ara..."
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          {/* Date from */}
          <div className="flex-shrink-0">
            <label
              htmlFor="fromDate"
              className="mb-1.5 block text-xs font-medium text-slate-600"
            >
              <Calendar className="inline h-3.5 w-3.5 mr-1" />
              Başlangıç
            </label>
            <input
              id="fromDate"
              type="date"
              value={fromDate}
              onChange={(e) => {
                setFromDate(e.target.value)
                setPage(1)
              }}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          {/* Date to */}
          <div className="flex-shrink-0">
            <label
              htmlFor="toDate"
              className="mb-1.5 block text-xs font-medium text-slate-600"
            >
              <Calendar className="inline h-3.5 w-3.5 mr-1" />
              Bitiş
            </label>
            <input
              id="toDate"
              type="date"
              value={toDate}
              onChange={(e) => {
                setToDate(e.target.value)
                setPage(1)
              }}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>
        </div>
      </div>

      {/* Sessions table */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200/60 overflow-hidden">
        {/* Table header */}
        <div className="grid grid-cols-[1fr_1fr_0.8fr_0.8fr_0.6fr_auto] gap-4 border-b border-slate-200 bg-slate-50 px-4 py-3">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Tarih
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Doktor
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Ziyaret Tipi
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Durum
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Süre
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          </span>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center p-12">
            <div className="flex flex-col items-center gap-2">
              <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
              <p className="text-sm text-slate-500">Görüşmeler yükleniyor...</p>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-3 p-6">
            <AlertCircle className="h-5 w-5 text-red-500 shrink-0" />
            <p className="text-sm text-red-700">
              Görüşmeler yüklenirken hata oluştu:{' '}
              {error instanceof Error ? error.message : 'Bilinmeyen hata'}
            </p>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && sessions.length === 0 && (
          <div className="flex flex-col items-center justify-center p-12">
            <p className="text-sm text-slate-500">Görüşme bulunamadı</p>
            <p className="text-xs text-slate-400 mt-1">Filtrelerinizi değiştirmeyi deneyin</p>
          </div>
        )}

        {/* Rows */}
        {!isLoading &&
          !error &&
          sessions.map((session) => (
            <div
              key={session.id}
              className="grid grid-cols-[1fr_1fr_0.8fr_0.8fr_0.6fr_auto] gap-4 w-full items-center border-b border-slate-100 px-4 py-3 text-left transition-colors hover:bg-slate-50 last:border-b-0 cursor-pointer"
              onClick={() => navigate(getSessionRoute(session))}
            >
              <span className="text-sm text-slate-700">
                {formatDateTime(session.created_at)}
              </span>
              <span className="text-sm font-medium text-slate-800 truncate">
                {session.doctor_name}
              </span>
              <span className="text-sm text-slate-600">
                {visitTypeLabels[session.visit_type]}
              </span>
              <StatusBadge status={session.status} />
              <span className="text-sm text-slate-500">
                {formatDuration(session.audio_duration_seconds)}
              </span>
              <button
                type="button"
                onClick={(e) => handleDelete(e, session.id)}
                disabled={deletingId === session.id}
                className="p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                title="Görüşmeyi arşivle"
              >
                {deletingId === session.id ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </button>
            </div>
          ))}
      </div>

      {/* Pagination info + controls */}
      {!isLoading && !error && (data?.total ?? 0) > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            Toplam {data?.total ?? 0} görüşme{totalPages > 1 ? `, Sayfa ${page}/${totalPages}` : ''}
          </p>
          {totalPages > 1 && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="h-4 w-4" />
                Önceki
              </button>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Sonraki
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
