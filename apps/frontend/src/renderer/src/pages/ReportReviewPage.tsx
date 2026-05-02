import { useState, useRef, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  FileText,
  GripVertical,
  Sparkles,
  AlertTriangle,
  Eye,
  EyeOff,
} from 'lucide-react'
import { apiClient } from '../services/apiClient'
import { ReportEditor } from '../components/report/ReportEditor'
import { TranscriptSegmentItem } from '../components/session/TranscriptSegment'
import { useT } from '../hooks/useT'
import type { SessionDetail } from '../types/session'
import type { Report } from '../types/report'
import { cn } from '../lib/utils'

export function ReportReviewPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const sessionId = id ? parseInt(id, 10) : null
  const t = useT()

  const [dividerPosition, setDividerPosition] = useState(50)
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const [selectedSegmentIndex, setSelectedSegmentIndex] = useState<number | null>(null)
  // Doctors review the structured report, not the raw transcript. Hide it by
  // default; expose a toggle for the rare case it's needed (auditing, training).
  const [showTranscript, setShowTranscript] = useState(false)

  const { data: session, isLoading, error } = useQuery<SessionDetail>({
    queryKey: ['session', sessionId],
    queryFn: () => apiClient.get<SessionDetail>(`/api/v1/sessions/${sessionId}`),
    enabled: sessionId !== null,
  })

  const generateReport = useMutation({
    mutationFn: () =>
      apiClient.post<Report>('/api/v1/reports', { session_id: sessionId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
    },
  })

  const generateAIReport = useMutation({
    mutationFn: () =>
      apiClient.post<Report>('/api/v1/reports', {
        session_id: sessionId,
        method: 'ai_generated',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
    },
  })

  const handleMouseDown = useCallback(() => {
    setIsDragging(true)
  }, [])

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e: MouseEvent): void => {
      const container = containerRef.current
      if (!container) return
      const rect = container.getBoundingClientRect()
      const percentage = ((e.clientX - rect.left) / rect.width) * 100
      setDividerPosition(Math.max(25, Math.min(75, percentage)))
    }

    const handleMouseUp = (): void => {
      setIsDragging(false)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          <p className="text-sm text-slate-500 dark:text-slate-400">{t('review_loading')}</p>
        </div>
      </div>
    )
  }

  if (error || !session) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex items-center gap-3 rounded-xl bg-red-50 dark:bg-red-900/30 p-6 ring-1 ring-red-200 dark:ring-red-800">
          <AlertCircle className="h-5 w-5 text-red-500 shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-200">{t('review_loadError')}</p>
            <p className="text-sm text-red-600 mt-1">
              {error instanceof Error ? error.message : t('review_unknownError')}
            </p>
          </div>
        </div>
      </div>
    )
  }

  const reports = session.reports ?? []
  const report = reports.length > 0 ? reports[reports.length - 1] : null
  const segments = session.segments ?? []

  return (
    <div className="flex flex-col h-full -m-6">
      {/* Header bar */}
      <div className="flex items-center gap-3 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2.5 shrink-0">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="rounded-lg p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700  hover:text-slate-700 dark:hover:text-slate-100  transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-sm font-bold text-slate-800 dark:text-slate-100">
            {t('review_title', { doctorName: session.doctor_name })}
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t('review_patient')} {session.patient_name || session.patient_id || t('review_notSpecified')}
          </p>
        </div>
        {/* Transcript visibility toggle */}
        {segments.length > 0 && (
          <button
            type="button"
            onClick={() => setShowTranscript((v) => !v)}
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-600 px-2.5 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
            title={showTranscript ? t('review_hideTranscript') : t('review_showTranscript')}
          >
            {showTranscript ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            {showTranscript ? t('review_hideTranscript') : t('review_showTranscript')}
          </button>
        )}
        {/* AI generate button - always visible when segments exist */}
        {segments.length > 0 && (
          <button
            type="button"
            onClick={() => generateAIReport.mutate()}
            disabled={generateAIReport.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-violet-700 disabled:opacity-50"
          >
            {generateAIReport.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            {report ? t('review_regenerate') : t('review_generate')}
          </button>
        )}
      </div>

      {/* Split panel */}
      <div
        ref={containerRef}
        className={cn('flex flex-1 overflow-hidden', isDragging && 'select-none cursor-col-resize')}
      >
        {/* Left panel - Transcript (toggleable; hidden by default).
            When hidden, the right panel takes the full width via flex-1. */}
        {showTranscript && (
          <div
            className="flex flex-col overflow-hidden border-r border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 shrink-0"
            style={{ width: `${dividerPosition}%` }}
          >
            <div className="border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3 shrink-0">
              <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{t('review_transcript')}</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {t('review_segments', { count: segments.length })}
              </p>
            </div>

            <div className="flex-1 overflow-auto">
              {segments.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-slate-500 dark:text-slate-400">{t('review_transcriptNotFound')}</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-700">
                  {segments.map((segment, index) => (
                    <button
                      key={segment.id}
                      type="button"
                      onClick={() =>
                        setSelectedSegmentIndex(
                          index === selectedSegmentIndex ? null : index
                        )
                      }
                      className={cn(
                        'w-full text-left transition-colors',
                        index === selectedSegmentIndex && 'ring-2 ring-inset ring-blue-300 bg-blue-50/50 dark:bg-blue-900/20'
                      )}
                    >
                      <TranscriptSegmentItem segment={segment} index={index} />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Resizable divider — only visible when both panels are shown */}
        {showTranscript && (
          <div
            onMouseDown={handleMouseDown}
            className="flex items-center justify-center w-2 bg-slate-200 dark:bg-slate-700 hover:bg-blue-300 cursor-col-resize transition-colors shrink-0"
          >
            <GripVertical className="h-4 w-4 text-slate-400 dark:text-slate-500" />
          </div>
        )}

        {/* Right panel - Report.
            When transcript is hidden, fills the full width (flex-1).
            When shown, takes the complementary share of the divider. */}
        <div
          className="flex flex-col overflow-hidden bg-slate-50 dark:bg-slate-900 flex-1"
          style={showTranscript ? { width: `${100 - dividerPosition}%`, flex: 'none' } : undefined}
        >
          {report ? (
            <ReportEditor report={report} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-700">
                <FileText className="h-8 w-8 text-slate-400 dark:text-slate-500" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-200">{t('review_noReport')}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{t('review_generateHint')}</p>
              </div>

              {/* AI Generate button */}
              <button
                type="button"
                onClick={() => generateAIReport.mutate()}
                disabled={generateAIReport.isPending || segments.length === 0}
                className="flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-violet-700 disabled:opacity-50"
              >
                {generateAIReport.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {t('review_generate')}
              </button>

              {segments.length === 0 && (
                <div className="flex items-center gap-2 rounded-lg bg-amber-50 dark:bg-amber-900/30 px-4 py-2 ring-1 ring-amber-200 dark:ring-amber-800">
                  <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
                  <p className="text-xs text-amber-700 dark:text-amber-300">{t('review_transcriptRequired')}</p>
                </div>
              )}

              {/* Manual (empty) generate button */}
              <button
                type="button"
                onClick={() => generateReport.mutate()}
                disabled={generateReport.isPending}
                className="flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-600 px-5 py-2.5 text-sm font-medium text-slate-700 dark:text-slate-200 shadow-sm transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/50  disabled:opacity-50"
              >
                {generateReport.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                {t('review_createBlank')}
              </button>

              {(generateReport.isError || generateAIReport.isError) && (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 dark:bg-red-900/30 px-4 py-2 ring-1 ring-red-200 dark:ring-red-800">
                  <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
                  <p className="text-xs text-red-700 dark:text-red-300">
                    {(generateAIReport.error ?? generateReport.error) instanceof Error
                      ? ((generateAIReport.error ?? generateReport.error) as Error).message
                      : t('review_reportFailed')}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
