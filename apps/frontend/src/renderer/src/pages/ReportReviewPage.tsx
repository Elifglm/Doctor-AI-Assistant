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
} from 'lucide-react'
import { apiClient } from '../services/apiClient'
import { ReportEditor } from '../components/report/ReportEditor'
import { TranscriptSegmentItem } from '../components/session/TranscriptSegment'
import type { SessionDetail } from '../types/session'
import type { Report } from '../types/report'
import { cn } from '../lib/utils'

export function ReportReviewPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const sessionId = id ? parseInt(id, 10) : null

  const [dividerPosition, setDividerPosition] = useState(50)
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const [selectedSegmentIndex, setSelectedSegmentIndex] = useState<number | null>(null)

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
          <p className="text-sm text-slate-500">Görüşme yükleniyor...</p>
        </div>
      </div>
    )
  }

  if (error || !session) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex items-center gap-3 rounded-xl bg-red-50 p-6 ring-1 ring-red-200">
          <AlertCircle className="h-5 w-5 text-red-500 shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-800">Görüşme yüklenemedi</p>
            <p className="text-sm text-red-600 mt-1">
              {error instanceof Error ? error.message : 'Bilinmeyen hata'}
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
      <div className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-2.5 shrink-0">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-sm font-bold text-slate-800">
            Rapor İnceleme - {session.doctor_name}
          </h1>
          <p className="text-xs text-slate-500">
            Hasta: {session.patient_name || session.patient_id || 'Belirtilmemiş'}
          </p>
        </div>
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
            {report ? 'AI ile Yeniden Oluştur' : 'AI ile Oluştur'}
          </button>
        )}
      </div>

      {/* Split panel */}
      <div
        ref={containerRef}
        className={cn('flex flex-1 overflow-hidden', isDragging && 'select-none cursor-col-resize')}
      >
        {/* Left panel - Transcript */}
        <div
          className="flex flex-col overflow-hidden border-r border-slate-200 bg-slate-50"
          style={{ width: `${dividerPosition}%` }}
        >
          <div className="border-b border-slate-200 bg-white px-4 py-3 shrink-0">
            <h2 className="text-lg font-semibold text-slate-800">Transkript</h2>
            <p className="text-xs text-slate-500 mt-0.5">{segments.length} segment</p>
          </div>

          <div className="flex-1 overflow-auto">
            {segments.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <p className="text-sm text-slate-500">Transkript bulunamadı</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
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
                      index === selectedSegmentIndex && 'ring-2 ring-inset ring-blue-300 bg-blue-50/50'
                    )}
                  >
                    <TranscriptSegmentItem segment={segment} index={index} />
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Resizable divider */}
        <div
          onMouseDown={handleMouseDown}
          className="flex items-center justify-center w-2 bg-slate-200 hover:bg-blue-300 cursor-col-resize transition-colors shrink-0"
        >
          <GripVertical className="h-4 w-4 text-slate-400" />
        </div>

        {/* Right panel - Report */}
        <div
          className="flex flex-col overflow-hidden bg-slate-50"
          style={{ width: `${100 - dividerPosition}%` }}
        >
          {report ? (
            <ReportEditor
              report={report}
              transcriptText={segments.map((s) => `${s.speaker_label}: ${s.text}`).join('\n')}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-100">
                <FileText className="h-8 w-8 text-slate-400" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-slate-700">
                  Henüz rapor oluşturulmamış
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Transkriptten otomatik veya boş rapor oluşturun
                </p>
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
                AI ile Oluştur
              </button>

              {segments.length === 0 && (
                <div className="flex items-center gap-2 rounded-lg bg-amber-50 px-4 py-2 ring-1 ring-amber-200">
                  <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
                  <p className="text-xs text-amber-700">
                    AI rapor oluşturmak için transkript gereklidir
                  </p>
                </div>
              )}

              {/* Manual (empty) generate button */}
              <button
                type="button"
                onClick={() => generateReport.mutate()}
                disabled={generateReport.isPending}
                className="flex items-center gap-2 rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 disabled:opacity-50"
              >
                {generateReport.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                Boş Şablon Oluştur
              </button>

              {(generateReport.isError || generateAIReport.isError) && (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 px-4 py-2 ring-1 ring-red-200">
                  <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
                  <p className="text-xs text-red-700">
                    {(generateAIReport.error ?? generateReport.error) instanceof Error
                      ? ((generateAIReport.error ?? generateReport.error) as Error).message
                      : 'Rapor oluşturulamadı'}
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
