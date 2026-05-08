import { useEffect } from 'react'
import { ShieldAlert, X } from 'lucide-react'
import { useT } from '../../hooks/useT'

interface KvkkConsentModalProps {
  open: boolean
  onClose: () => void
  onAccept: () => void
}

export function KvkkConsentModal({ open, onClose, onAccept }: KvkkConsentModalProps): React.JSX.Element | null {
  const t = useT()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="kvkk-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-3xl max-h-[90vh] flex-col rounded-xl bg-white dark:bg-slate-800 shadow-xl ring-1 ring-slate-200/60 dark:ring-slate-700/60"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/40">
              <ShieldAlert className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h2 id="kvkk-modal-title" className="text-lg font-semibold text-slate-800 dark:text-slate-100">
              {t('kvkk_modalTitle')}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
            aria-label={t('confirm_cancel')}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4 text-sm text-slate-700 dark:text-slate-200">
          <div className="rounded-lg border-2 border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 p-3 text-xs font-medium text-amber-800 dark:text-amber-200">
            {t('kvkk_legalDisclaimer')}
          </div>

          <p className="leading-relaxed whitespace-pre-line">{t('kvkk_intro')}</p>

          <Section title={t('kvkk_h1_controller')} body={t('kvkk_b1_controller')} />
          <Section title={t('kvkk_h2_dataTypes')} body={t('kvkk_b2_dataTypes')} />
          <Section title={t('kvkk_h3_purposes')} body={t('kvkk_b3_purposes')} />
          <Section title={t('kvkk_h4_transfers')} body={t('kvkk_b4_transfers')} />
          <Section title={t('kvkk_h5_retention')} body={t('kvkk_b5_retention')} />
          <Section title={t('kvkk_h6_rights')} body={t('kvkk_b6_rights')} />
          <Section title={t('kvkk_h7_consent')} body={t('kvkk_b7_consent')} />
        </div>

        {/* Footer */}
        <div className="flex flex-col gap-2 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-6 py-4 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-600 transition-colors"
          >
            {t('kvkk_decline')}
          </button>
          <button
            type="button"
            onClick={() => {
              onAccept()
              onClose()
            }}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 transition-colors"
          >
            {t('kvkk_accept')}
          </button>
        </div>
      </div>
    </div>
  )
}

function Section({ title, body }: { title: string; body: string }): React.JSX.Element {
  return (
    <div>
      <h3 className="mb-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h3>
      <p className="leading-relaxed whitespace-pre-line text-slate-600 dark:text-slate-300">{body}</p>
    </div>
  )
}
