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
import { useT } from '../hooks/useT'
import type { Session, SessionListResponse, SessionStatus, VisitType } from '../types/session'

function formatDateTime(isoString: string): string {
  const date = new Date(isoString)
  const day = date.getDate().toString().padStart(2, '0')
  const month = (date.getMonth() + 1).toString().padStart(2, '0')
  const year = date.getFullYear()
  const hours = date.getHours().toString().padStart(2, '0')
  const minutes = date.getMinutes().toString().padStart(2, '0')
  return `${day}.${month}.${year} ${hours}:${minutes}`
}

function formatDuration(seconds: number | null, minLabel: string, secLabel: string): string {
  if (seconds === null) return '-'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}${minLabel} ${secs}${secLabel}`
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
  const t = useT()

  const statusFilterOptions: { value: string; labelKey: string }[] = [
    { value: '', labelKey: 'history_all' },
    { value: 'AWAITING_REVIEW', labelKey: 'history_pending' },
    { value: 'COMPLETED', labelKey: 'history_completed' },
    { value: 'ARCHIVED', labelKey: 'history_archived' },
  ]

  const visitTypeLabelKeys: Record<VisitType, string> = {
    ilk_muayene: 'history_visitType_ilkMuayene',
    kontrol: 'history_visitType_kontrol',
    konsultasyon: 'history_visitType_konsultasyon',
    acil: 'history_visitType_acil',
  }

  const handleDelete = useCallback(async (e: React.MouseEvent, sessionId: number) => {
    e.stopPropagation()
    if (!confirm(t('history_archiveConfirm'))) return
    setDeletingId(sessionId)
    try {
      await apiClient.delete(`/api/v1/sessions/${sessionId}`)
      queryClient.invalidateQueries({ queryKey: ['sessions-history'] })
    } catch (err) {
      console.error('Silme hatasi:', err)
      alert(t('history_deleteError'))
    } finally {
      setDeletingId(null)
    }
  }, [queryClient, t])

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
        <h1 className="text-2xl font-bold text-slate-800">{t('history_title')}</h1>
        <p className="text-sm text-slate-500 mt-1">{t('history_subtitle')}</p>
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
              {t('history_status')}
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
                  {t(opt.labelKey)}
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
              {t('history_search')}
            </label>
            <input
              id="searchInput"
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              placeholder={t('history_searchPlaceholder')}
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
              {t('history_startDate')}
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
              {t('history_endDate')}
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
            {t('history_col_date')}
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            {t('history_col_doctor')}
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            {t('history_col_visitType')}
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            {t('history_col_status')}
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            {t('history_col_duration')}
          </span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider" />
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center p-12">
            <div className="flex flex-col items-center gap-2">
              <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
              <p className="text-sm text-slate-500">{t('history_loading')}</p>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-3 p-6">
            <AlertCircle className="h-5 w-5 text-red-500 shrink-0" />
            <p className="text-sm text-red-700">
              {t('history_loadError')}{' '}
              {error instanceof Error ? error.message : t('history_unknownError')}
            </p>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && sessions.length === 0 && (
          <div className="flex flex-col items-center justify-center p-12">
            <p className="text-sm text-slate-500">{t('history_noSessions')}</p>
            <p className="text-xs text-slate-400 mt-1">{t('history_noSessionsHint')}</p>
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
                {t(visitTypeLabelKeys[session.visit_type])}
              </span>
              <StatusBadge status={session.status} />
              <span className="text-sm text-slate-500">
                {formatDuration(session.audio_duration_seconds, t('history_min'), t('history_sec'))}
              </span>
              <button
                type="button"
                onClick={(e) => handleDelete(e, session.id)}
                disabled={deletingId === session.id}
                className="p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                title={t('history_archiveTooltip')}
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
            {t('history_total', { total: data?.total ?? 0 })}
            {totalPages > 1 ? t('history_page', { page, totalPages }) : ''}
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
                {t('history_prev')}
              </button>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t('history_next')}
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
