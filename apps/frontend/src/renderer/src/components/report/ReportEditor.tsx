import { useState, useCallback, useEffect, useRef } from 'react'
import { Save, CheckCheck, Loader2, FileDown, Send, CheckCircle2, AlertCircle } from 'lucide-react'
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
  const [icdWarning, setIcdWarning] = useState(false)
  const [pdfWarning, setPdfWarning] = useState(false)
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

  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false)

  const handleDownloadPdf = async (): Promise<void> => {
    setIsDownloadingPdf(true)
    try {
      const token = (await import('../../stores/authStore')).useAuthStore.getState().token
      const baseUrl = 'http://127.0.0.1:8700'
      const res = await fetch(`${baseUrl}/api/v1/reports/${report.id}/pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('PDF indirilemedi')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `anamnez_rapor_${report.id}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF download error:', err)
      alert('PDF indirme hatasi')
    } finally {
      setIsDownloadingPdf(false)
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
          message: `OpenEMR'e gonderildi (Encounter #${res.encounter_id}, ${res.icd10_count} ICD-10 kodu)`,
        })
      } else {
        setOpenEMRResult({ success: false, message: res.error || 'Gonderim basarisiz' })
      }
    } catch (err) {
      setOpenEMRResult({
        success: false,
        message: err instanceof Error ? err.message : 'OpenEMR baglanti hatasi',
      })
    } finally {
      setIsPushingOpenEMR(false)
    }
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
            allSections={sections}
            sessionId={report.session_id}
          />
        ))}
      </div>

      <div className="border-t border-slate-200 bg-white px-4 py-3 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1">
            <div className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-xs text-slate-600 whitespace-nowrap">
              {approvedCount}/{totalCount} bolum onaylandi
            </span>
          </div>
          {showSuccess && (
            <span className="text-xs text-emerald-600">Kaydedildi</span>
          )}
          {showError && (
            <span className="text-xs text-red-600">Kaydetme hatasi</span>
          )}
          {icdWarning && (
            <span className="text-xs text-amber-600 font-medium">ICD-10 tani kodu seciniz</span>
          )}
          {pdfWarning && (
            <span className="text-xs text-red-600 font-medium">
              PDF icin tum bolumleri onaylayin ({approvedCount}/{totalCount})
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => {
              if (approvedCount < totalCount) {
                setPdfWarning(true)
                setTimeout(() => setPdfWarning(false), 5000)
                return
              }
              void handleDownloadPdf()
            }}
            disabled={isDownloadingPdf}
            title={approvedCount < totalCount ? `${totalCount - approvedCount} bolum henuz onaylanmadi` : 'PDF olarak indir'}
            className={`flex items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 whitespace-nowrap ${
              approvedCount < totalCount
                ? 'border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed'
                : 'border-blue-300 bg-blue-50 text-blue-700 hover:bg-blue-100'
            }`}
          >
            {isDownloadingPdf ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileDown className="h-4 w-4" />
            )}
            PDF Indir
          </button>
          <button
            type="button"
            onClick={handleSaveDraft}
            disabled={saveMutation.isPending}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Taslagi Kaydet
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
            {approvedCount === totalCount ? 'Tumu Onaylandi' : 'Tumunu Onayla'}
          </button>
          <button
            type="button"
            onClick={() => {
              if (approvedCount < totalCount) {
                setPdfWarning(true)
                setTimeout(() => setPdfWarning(false), 5000)
                return
              }
              void handlePushToOpenEMR()
            }}
            disabled={isPushingOpenEMR}
            title={approvedCount < totalCount ? `${totalCount - approvedCount} bolum henuz onaylanmadi` : 'Raporu OpenEMR sistemine gonder'}
            className={`flex items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 whitespace-nowrap ${
              approvedCount < totalCount
                ? 'border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed'
                : 'border-purple-300 bg-purple-600 text-white hover:bg-purple-700'
            }`}
          >
            {isPushingOpenEMR ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            OpenEMR'e Gonder
          </button>
        </div>
      </div>

      {/* OpenEMR push result */}
      {openEMRResult && (
        <div
          className={`flex items-center gap-2 px-4 py-2.5 text-sm border-t ${
            openEMRResult.success
              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
              : 'bg-red-50 text-red-700 border-red-200'
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
    </div>
  )
}
