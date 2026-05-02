import { useState, useCallback, useEffect, useRef } from 'react'
import { Save, CheckCheck, Loader2, FileText, Send, CheckCircle2, AlertCircle } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ReportSectionCard } from './ReportSection'
import { PdfPreviewModal } from './PdfPreviewModal'
import { apiClient } from '../../services/apiClient'
import { useT } from '../../hooks/useT'
import type { Report, ReportSection } from '../../types/report'

interface ReportEditorProps {
  report: Report
}

export function ReportEditor({ report }: ReportEditorProps): React.JSX.Element {
  const queryClient = useQueryClient()
  const t = useT()
  const [sections, setSections] = useState<ReportSection[]>(report.content.sections)

  const [showSuccess, setShowSuccess] = useState(false)
  const [showError, setShowError] = useState(false)
  const [icdWarning, setIcdWarning] = useState(false)
  const [openEmrWarning, setOpenEmrWarning] = useState(false)
  const [isPushingOpenEMR, setIsPushingOpenEMR] = useState(false)
  const [openEMRResult, setOpenEMRResult] = useState<{ success: boolean; message: string } | null>(null)
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
        if (s.content === content) return s
        return { ...s, content, status: s.status === 'approved' ? 'edited' as const : s.status }
      })
    )
  }, [])

  const handleApprove = useCallback((key: string) => {
    setSections((prev) =>
      prev.map((s) => (s.key === key ? { ...s, status: 'approved' as const } : s))
    )
  }, [])

  // Revert an approved section back to "edited" so the doctor can change it.
  // Without this, clicking "Düzenle" on an approved section did nothing — the
  // old handler routed through onContentChange which short-circuits when the
  // text hasn't changed.
  const handleUnapprove = useCallback((key: string) => {
    setSections((prev) =>
      prev.map((s) => (s.key === key ? { ...s, status: 'edited' as const } : s))
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
    const icdSection = sections.find((s) => s.key === 'icd10_list')
    if (icdSection && (!icdSection.content || icdSection.content === 'BELIRTILMEDI')) {
      setIcdWarning(true)
      setTimeout(() => setIcdWarning(false), 5000)
      return
    }

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

  const [showPdfPreview, setShowPdfPreview] = useState(false)
  const [isOpeningPreview, setIsOpeningPreview] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)

  const handleOpenPdfPreview = async (): Promise<void> => {
    // Save current state silently first so the preview reflects latest edits.
    setIsOpeningPreview(true)
    setPdfError(null)
    try {
      await apiClient.put<Report>(`/api/v1/reports/${report.id}`, {
        content: {
          sections,
          approved_sections: sections.filter((s) => s.status === 'approved').length,
          total_sections: sections.length,
        },
      })
      setShowPdfPreview(true)
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : t('report_pdfDownloadError'))
      setTimeout(() => setPdfError(null), 5000)
    } finally {
      setIsOpeningPreview(false)
    }
  }

  const handlePushToOpenEMR = async (): Promise<void> => {
    setIsPushingOpenEMR(true)
    setOpenEMRResult(null)
    try {
      const res = await apiClient.post<{
        success: boolean
        encounter_id: number
        icd10_count: number
        error: string
      }>(`/api/v1/reports/${report.id}/push-to-openemr`)
      if (res.success) {
        setOpenEMRResult({
          success: true,
          message: t('report_sentToOpenEMR', {
            encounterId: res.encounter_id,
            icd10Count: res.icd10_count,
          }),
        })
      } else {
        setOpenEMRResult({ success: false, message: res.error || t('report_sendFailed') })
      }
    } catch (err) {
      setOpenEMRResult({
        success: false,
        message: err instanceof Error ? err.message : t('report_connectionError'),
      })
    } finally {
      setIsPushingOpenEMR(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3">
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{t('report_title')}</h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          {t('report_sectionsApproved', { approved: approvedCount, total: totalCount })}
        </p>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-3">
        {sections.map((section) => (
          <ReportSectionCard
            key={section.key}
            section={section}
            onContentChange={handleContentChange}
            onApprove={handleApprove}
            onUnapprove={handleUnapprove}
            allSections={sections}
            sessionId={report.session_id}
          />
        ))}
      </div>

      <div className="border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1">
            <div className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-xs text-slate-600 dark:text-slate-300 whitespace-nowrap">
              {t('report_sectionsApproved', { approved: approvedCount, total: totalCount })}
            </span>
          </div>
          {showSuccess && (
            <span className="text-xs text-emerald-600">{t('report_saved')}</span>
          )}
          {showError && (
            <span className="text-xs text-red-600">{t('report_saveError')}</span>
          )}
          {icdWarning && (
            <span className="text-xs text-amber-600 font-medium">{t('report_icd10Placeholder')}</span>
          )}
          {pdfError && (
            <span className="text-xs text-red-600 font-medium">{pdfError}</span>
          )}
          {openEmrWarning && (
            <span className="text-xs text-red-600 font-medium">
              {t('report_sectionsNotApproved', { count: totalCount - approvedCount })}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => void handleOpenPdfPreview()}
            disabled={isOpeningPreview}
            title={t('report_pdfPreviewTitle')}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/50 px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            {isOpeningPreview ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileText className="h-4 w-4" />
            )}
            {t('report_pdfPreview')}
          </button>
          <button
            type="button"
            onClick={handleSaveDraft}
            disabled={saveMutation.isPending}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/50  transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {t('report_saveDraft')}
          </button>
          <button
            type="button"
            onClick={handleApproveAll}
            disabled={saveMutation.isPending || approvedCount === totalCount}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-emerald-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCheck className="h-4 w-4" />
            )}
            {approvedCount === totalCount ? t('report_allApproved') : t('report_approveAll')}
          </button>
          <button
            type="button"
            onClick={() => {
              if (approvedCount < totalCount) {
                setOpenEmrWarning(true)
                setTimeout(() => setOpenEmrWarning(false), 5000)
                return
              }
              void handlePushToOpenEMR()
            }}
            disabled={isPushingOpenEMR}
            title={approvedCount < totalCount
              ? t('report_sectionsNotApproved', { count: totalCount - approvedCount })
              : t('report_sendTooltip')}
            className={`flex items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 whitespace-nowrap ${
              approvedCount < totalCount
                ? 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-400 dark:text-slate-500 cursor-not-allowed'
                : 'border-purple-300 bg-purple-600 text-white hover:bg-purple-700'
            }`}
          >
            {isPushingOpenEMR ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            {t('report_sendToOpenEMR')}
          </button>
        </div>
      </div>

      {/* OpenEMR push result */}
      {openEMRResult && (
        <div
          className={`flex items-center gap-2 px-4 py-2.5 text-sm border-t ${
            openEMRResult.success
              ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
              : 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800'
          }`}
        >
          {openEMRResult.success ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 shrink-0" />
          )}
          <span>{openEMRResult.message}</span>
        </div>
      )}

      {showPdfPreview && (
        <PdfPreviewModal
          reportId={report.id}
          onClose={() => setShowPdfPreview(false)}
        />
      )}
    </div>
  )
}
