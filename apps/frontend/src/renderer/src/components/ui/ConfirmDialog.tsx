import { useEffect, useRef } from 'react'
import { AlertTriangle } from 'lucide-react'
import { useConfirmStore } from '../../stores/confirmStore'
import { useT } from '../../hooks/useT'
import { cn } from '../../lib/utils'

export function ConfirmDialog(): React.JSX.Element | null {
  const open = useConfirmStore((s) => s.open)
  const options = useConfirmStore((s) => s.options)
  const resolve = useConfirmStore((s) => s.resolve)
  const t = useT()
  const confirmBtnRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') resolve(false)
      if (e.key === 'Enter') resolve(true)
    }
    window.addEventListener('keydown', onKey)
    confirmBtnRef.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [open, resolve])

  if (!open || !options) return null

  const isDanger = options.variant === 'danger'

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={() => resolve(false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-xl bg-white dark:bg-slate-800 p-6 shadow-xl ring-1 ring-slate-200/60 dark:ring-slate-700/60"
      >
        <div className="mb-4 flex items-center gap-3">
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-full',
              isDanger ? 'bg-red-100 dark:bg-red-900/40' : 'bg-amber-100 dark:bg-amber-900/40',
            )}
          >
            <AlertTriangle
              className={cn(
                'h-5 w-5',
                isDanger ? 'text-red-600 dark:text-red-400' : 'text-amber-600 dark:text-amber-400',
              )}
            />
          </div>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
            {options.title}
          </h2>
        </div>
        <p className="mb-6 text-sm text-slate-600 dark:text-slate-300 whitespace-pre-line">
          {options.message}
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={() => resolve(false)}
            className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-600 transition-colors"
          >
            {options.cancelText ?? t('confirm_cancel')}
          </button>
          <button
            ref={confirmBtnRef}
            type="button"
            onClick={() => resolve(true)}
            className={cn(
              'rounded-lg px-4 py-2 text-sm font-semibold text-white transition-colors',
              isDanger ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700',
            )}
          >
            {options.confirmText ?? t('confirm_ok')}
          </button>
        </div>
      </div>
    </div>
  )
}
