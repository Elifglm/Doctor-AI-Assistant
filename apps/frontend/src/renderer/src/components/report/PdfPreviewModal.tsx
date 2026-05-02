import { useEffect, useState, useCallback, useRef } from 'react'
import { X, RefreshCw, Loader2, AlertCircle } from 'lucide-react'
import { useAuthStore } from '../../stores/authStore'
import { useT } from '../../hooks/useT'

interface PdfPreviewModalProps {
  reportId: number
  onClose: () => void
}

export function PdfPreviewModal({ reportId, onClose }: PdfPreviewModalProps): React.JSX.Element {
  const t = useT()
  // Capture t in a ref so loadPdf isn't re-created on every render (which would
  // trigger an effect loop -> infinite PDF re-fetch -> "flickering" black screen).
  const tRef = useRef(t)
  tRef.current = t
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadPdf = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const token = useAuthStore.getState().token
      const baseUrl =
        (typeof window !== 'undefined' && window.electronAPI?.getBackendUrl()) ||
        'http://127.0.0.1:8700'
      const res = await fetch(`${baseUrl}/api/v1/reports/${reportId}/pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error(tRef.current('report_pdfDownloadError'))
      const buffer = await res.arrayBuffer()
      // Use a data URL instead of a blob URL — sandboxed Electron renderers
      // refuse to load blob: PDFs in iframes (ERR_FILE_NOT_FOUND), but data:
      // URIs render reliably through the built-in Chromium PDF viewer.
      const bytes = new Uint8Array(buffer)
      let binary = ''
      const chunkSize = 0x8000
      for (let i = 0; i < bytes.length; i += chunkSize) {
        binary += String.fromCharCode.apply(
          null,
          Array.from(bytes.subarray(i, i + chunkSize)),
        )
      }
      const base64 = btoa(binary)
      setPdfUrl(`data:application/pdf;base64,${base64}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : tRef.current('report_pdfDownloadError'))
    } finally {
      setLoading(false)
    }
  }, [reportId])

  useEffect(() => {
    void loadPdf()
  }, [loadPdf])

  // Esc to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex flex-col w-full max-w-5xl h-[90vh] rounded-xl bg-white dark:bg-slate-800 shadow-2xl ring-1 ring-slate-200/60 dark:ring-slate-700/60 overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-4 py-3 shrink-0">
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">
            {t('report_pdfPreviewTitle')}
          </h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadPdf()}
              disabled={loading}
              title={t('report_pdfRefresh')}
              className="flex items-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors disabled:opacity-50"
            >
              {loading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              {t('report_pdfRefresh')}
            </button>
            <button
              type="button"
              onClick={onClose}
              title={t('report_pdfClose')}
              className="rounded-lg p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="relative flex-1 bg-slate-100 dark:bg-slate-900">
          {loading && !pdfUrl && (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {t('report_pdfLoading')}
              </p>
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center justify-center h-full gap-3 p-6">
              <div className="flex items-center gap-2 rounded-lg bg-red-50 dark:bg-red-900/30 px-4 py-3 ring-1 ring-red-200 dark:ring-red-800 max-w-md">
                <AlertCircle className="h-5 w-5 text-red-500 shrink-0" />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
              <button
                type="button"
                onClick={() => void loadPdf()}
                className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
              >
                <RefreshCw className="h-4 w-4" />
                {t('report_pdfRefresh')}
              </button>
            </div>
          )}

          {pdfUrl && !error && (
            <iframe
              src={pdfUrl}
              title={t('report_pdfPreviewTitle')}
              className="w-full h-full border-0"
            />
          )}
        </div>
      </div>
    </div>
  )
}
