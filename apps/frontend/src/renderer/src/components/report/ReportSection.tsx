import { useState, useRef, useEffect, useCallback } from 'react'
import { ChevronDown, ChevronRight, Check, Pencil } from 'lucide-react'
import { cn } from '../../lib/utils'
import { ConfidenceBadge } from './ConfidenceBadge'
import { ICD10Selector } from './ICD10Selector'
import { SutTetkikSelector } from './SutTetkikSelector'
import { useT } from '../../hooks/useT'
import type { ReportSection as ReportSectionType } from '../../types/report'

const statusConfig: Record<ReportSectionType['status'], { labelKey: string; className: string }> = {
  draft: {
    labelKey: 'report_section_draft',
    className: 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-300',
  },
  edited: {
    labelKey: 'report_section_edited',
    className: 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
  },
  approved: {
    labelKey: 'report_section_approved',
    className: 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300',
  },
}

interface ReportSectionProps {
  section: ReportSectionType
  onContentChange: (key: string, content: string) => void
  onApprove: (key: string) => void
  onUnapprove: (key: string) => void
  allSections?: ReportSectionType[]
  sessionId?: number
}

export function ReportSectionCard({
  section,
  onContentChange,
  onApprove,
  onUnapprove,
  allSections,
  sessionId,
}: ReportSectionProps): React.JSX.Element {
  const [isOpen, setIsOpen] = useState(true)
  const [icdWarning, setIcdWarning] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const t = useT()

  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${textarea.scrollHeight}px`
    }
  }, [])

  useEffect(() => {
    resizeTextarea()
  }, [section.content, isOpen, resizeTextarea])

  const status = statusConfig[section.status]

  return (
    <div className="rounded-xl bg-white dark:bg-slate-800 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-3">
          {isOpen ? (
            <ChevronDown className="h-4 w-4 text-slate-400 dark:text-slate-500" />
          ) : (
            <ChevronRight className="h-4 w-4 text-slate-400 dark:text-slate-500" />
          )}
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{section.title}</h3>
        </div>
        <div className="flex items-center gap-2">
          {section.confidence && <ConfidenceBadge confidence={section.confidence} />}
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
              status.className
            )}
          >
            {t(status.labelKey)}
          </span>
        </div>
      </button>

      {isOpen && (
        <div className="border-t border-slate-100 dark:border-slate-700 px-4 py-3 space-y-3">
          {section.key === 'icd10_list' ? (
            <ICD10Selector
              value={section.content}
              reportSections={allSections}
              onChange={(formatted) => onContentChange(section.key, formatted)}
            />
          ) : section.key === 'sut_tetkik_list' ? (
            <SutTetkikSelector
              value={section.content}
              reportSections={allSections}
              sessionId={sessionId}
              onChange={(formatted) => onContentChange(section.key, formatted)}
            />
          ) : (
            <textarea
              ref={textareaRef}
              value={section.content}
              onChange={(e) => {
                onContentChange(section.key, e.target.value)
                resizeTextarea()
              }}
              rows={3}
              className="w-full resize-none rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm text-slate-700 dark:text-slate-200 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              placeholder={t('report_section_placeholder')}
            />
          )}
          <div className="flex justify-end">
            {section.status === 'approved' ? (
              <button
                type="button"
                onClick={() => onUnapprove(section.key)}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-amber-700 dark:text-amber-300 ring-1 ring-amber-200 dark:ring-amber-800 hover:bg-amber-50 dark:hover:bg-amber-900/30 transition-colors"
              >
                <Pencil className="h-3.5 w-3.5" />
                {t('report_section_edit')}
              </button>
            ) : (
              <div className="flex items-center gap-2">
                {icdWarning && (
                  <span className="text-xs text-amber-600 font-medium">{t('report_section_icd10Required')}</span>
                )}
                <button
                  type="button"
                  onClick={() => {
                    if (section.key === 'icd10_list' && (!section.content || section.content === 'BELIRTILMEDI')) {
                      setIcdWarning(true)
                      setTimeout(() => setIcdWarning(false), 5000)
                      return
                    }
                    onApprove(section.key)
                  }}
                  className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-emerald-700 transition-colors"
                >
                  <Check className="h-3.5 w-3.5" />
                  {t('report_section_approve')}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
