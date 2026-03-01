import { useState, useCallback, useEffect, useRef } from 'react'
import { Save, CheckCheck, Loader2 } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ReportSectionCard } from './ReportSection'
import { apiClient } from '../../services/apiClient'
import type { Report, ReportSection } from '../../types/report'

interface ReportEditorProps {
  report: Report
}

export function ReportEditor({ report }: ReportEditorProps): React.JSX.Element {
  const queryClient = useQueryClient()
  const [sections, setSections] = useState<ReportSection[]>(report.content.sections)

  const [showSuccess, setShowSuccess] = useState(false)
  const [showError, setShowError] = useState(false)
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const approvedCount = sections.filter((s) => s.status === 'approved').length
  const totalCount = sections.length

  const saveMutation = useMutation({
    mutationFn: (payload: { content: Report['content']; status?: Report['status'] }) =>
      apiClient.put<Report>(`/api/v1/reports/${report.id}`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['session'] })
      setShowSuccess(true)
      setShowError(false)
      if (successTimerRef.current) clearTimeout(successTimerRef.current)
      successTimerRef.current = setTimeout(() => {
        setShowSuccess(false)
      }, 3000)
    },
    onError: () => {
      setShowError(true)
      setShowSuccess(false)
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
      errorTimerRef.current = setTimeout(() => {
        setShowError(false)
      }, 5000)
    },
  })

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (successTimerRef.current) clearTimeout(successTimerRef.current)
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
    }
  }, [])

  const handleContentChange = useCallback((key: string, content: string) => {
    setSections((prev) =>
      prev.map((s) => {
        if (s.key !== key) return s
        return { ...s, content, status: s.status === 'approved' ? 'edited' as const : s.status }
      })
    )
  }, [])

  const handleApprove = useCallback((key: string) => {
    setSections((prev) =>
      prev.map((s) => (s.key === key ? { ...s, status: 'approved' as const } : s))
    )
  }, [])

  const handleSaveDraft = (): void => {
    const approved = sections.filter((s) => s.status === 'approved').length
    saveMutation.mutate({
      content: {
        sections,
        approved_sections: approved,
        total_sections: sections.length,
      },
    })
  }

  const handleApproveAll = (): void => {
    const allApproved = sections.map((s) => ({ ...s, status: 'approved' as const }))
    setSections(allApproved)
    saveMutation.mutate({
      content: {
        sections: allApproved,
        approved_sections: allApproved.length,
        total_sections: allApproved.length,
      },
      status: 'APPROVED',
    })
  }

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-slate-200 bg-white px-4 py-3">
        <h2 className="text-lg font-semibold text-slate-800">Anamnez Raporu</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          {approvedCount}/{totalCount} bölüm onaylandı
        </p>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-3">
        {sections.map((section) => (
          <ReportSectionCard
            key={section.key}
            section={section}
            onContentChange={handleContentChange}
            onApprove={handleApprove}
          />
        ))}
      </div>

      <div className="border-t border-slate-200 bg-white px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <div className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-xs text-slate-600">
              {approvedCount}/{totalCount} bölüm onaylandı
            </span>
          </div>
          {showSuccess && (
            <span className="text-xs text-emerald-600 transition-opacity duration-200">Kaydedildi</span>
          )}
          {showError && (
            <span className="text-xs text-red-600 transition-opacity duration-200">Kaydetme hatası</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSaveDraft}
            disabled={saveMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
          >
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Taslağı Kaydet
          </button>
          <button
            type="button"
            onClick={handleApproveAll}
            disabled={saveMutation.isPending || approvedCount === totalCount}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCheck className="h-4 w-4" />
            )}
            Tümünü Onayla
          </button>
        </div>
      </div>
    </div>
  )
}
