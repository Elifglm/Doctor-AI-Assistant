import { useState, useRef, useEffect } from 'react'
import { Search, Sparkles, X, Loader2, Send, CheckCircle2, AlertCircle } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useSutTetkikSearch } from '../../hooks/useSutTetkikSearch'
import { apiClient } from '../../services/apiClient'
import { useAuthStore } from '../../stores/authStore'
import { useReportSuggestionStore } from '../../stores/reportSuggestionStore'
import { useT } from '../../hooks/useT'
import type {
  SUTConfirmedTetkik,
  SUTSuggestion,
  SUTSuggestResponse,
  SUTOpenEMRSendResponse,
} from '../../types/sut_tetkik'

interface ReportSectionData {
  key: string
  content: string
}

interface SutTetkikSelectorProps {
  value: string
  reportSections?: ReportSectionData[]
  brans?: string
  sessionId?: number
  onChange: (formatted: string) => void
}

interface ParsedTetkik extends SUTConfirmedTetkik {
  confidence?: number
}

function parseExistingTetkik(value: string): ParsedTetkik[] {
  if (!value || value === 'BELIRTILMEDI') return []
  const items: ParsedTetkik[] = []
  const lines = value.split('\n').filter((l) => l.trim())
  for (const line of lines) {
    const match = line.match(
      /^\(([A-Za-z0-9]+)\)\s*-\s*(.+?)(?:\s*\[%(\d+)\])?\s*$/
    )
    if (match) {
      const confidence = match[3] ? parseInt(match[3], 10) / 100 : undefined
      // Clean any remaining bracket artifacts from adi
      const adi = match[2].trim().replace(/\s*\[\]\s*$/, '')
      items.push({ kodu: match[1], adi, brans: '', confidence })
    }
  }
  return items
}

function formatTetkik(items: SUTConfirmedTetkik[]): string {
  if (items.length === 0) return ''
  return items
    .map((t) => `(${t.kodu}) - ${t.adi}`)
    .join('\n')
}

// Anamnez alanlarının (icd10/sut bölümleri hariç) parmak izi — "AI Tetkik
// Öner" butonunun yalnızca anamnez metni değiştiğinde aktif olması için.
function anamnesisFingerprint(sections?: ReportSectionData[]): string {
  if (!sections) return ''
  return sections
    .filter((s) => s.key !== 'icd10_list' && s.key !== 'sut_tetkik_list')
    .map((s) => s.content)
    .join('')
}

export function SutTetkikSelector({ value, reportSections, brans: bransProp, sessionId, onChange }: SutTetkikSelectorProps) {
  const t = useT()
  const storeSetSut = useReportSuggestionStore((s) => s.setSut)
  const parsed = parseExistingTetkik(value)
  const [selectedTetkik, setSelectedTetkik] = useState<SUTConfirmedTetkik[]>(() =>
    parsed.filter((p) => p.confidence === undefined).map(({ confidence: _, ...rest }) => rest)
  )
  const [searchQuery, setSearchQuery] = useState('')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  // Same threshold used in handleSuggest below — apply here too so reports
  // saved before the threshold existed don't surface stale low-confidence picks.
  const SUT_MIN_CONFIDENCE = 0.85
  const [suggestions, setSuggestions] = useState<SUTSuggestion[]>(() => {
    // "Geri" ile sayfadan çıkıp dönülünce öneriler kaybolmasın: önce session
    // bazlı önbelleğe bak, yoksa kayıtlı içerikten ayrıştır.
    const cached =
      sessionId != null ? useReportSuggestionStore.getState().sut[sessionId] : undefined
    if (cached) return cached
    return parsed
      .filter((p) => p.confidence !== undefined && p.confidence >= SUT_MIN_CONFIDENCE)
      .map((p) => ({
        kodu: p.kodu,
        adi: p.adi,
        brans: p.brans,
        confidence: p.confidence ?? 0.5,
        reasoning: '',
      }))
      .sort((a, b) => b.confidence - a.confidence)
  })
  const [isSuggesting, setIsSuggesting] = useState(false)
  // Son öneri anındaki anamnez parmak izi. Anamnez değişmediyse buton pasif.
  const [lastSuggestFingerprint, setLastSuggestFingerprint] = useState<string>(
    () => anamnesisFingerprint(reportSections),
  )
  const canSuggest =
    suggestions.length === 0 ||
    anamnesisFingerprint(reportSections) !== lastSuggestFingerprint
  const [isSendingToOpenEMR, setIsSendingToOpenEMR] = useState(false)
  const [openEMRResult, setOpenEMRResult] = useState<{
    success: boolean
    message: string
  } | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const user = useAuthStore((s) => s.user)

  // Doktorun branşına göre tetkik filtrele
  const brans = bransProp || user?.brans || undefined

  const { results, isLoading } = useSutTetkikSearch(searchQuery, brans)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const isInitialMount = useRef(true)
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false
      return
    }
    onChangeRef.current(formatTetkik(selectedTetkik))
  }, [selectedTetkik])

  // Kayıt sonrası otomatik gelen öneriler ilk yüklemede bölüm içeriğinden
  // ayrıştırılır. Bunları da bir kez store'a yaz ki içerik sonradan
  // (tetkik ekleme / kaydetme ile) değişse bile "geri" sonrası korunsunlar.
  useEffect(() => {
    if (
      sessionId != null &&
      suggestions.length > 0 &&
      useReportSuggestionStore.getState().sut[sessionId] === undefined
    ) {
      storeSetSut(sessionId, suggestions)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const addTetkik = (kodu: string, adi: string, tetkikBrans: string) => {
    if (selectedTetkik.some((t) => t.kodu === kodu)) return
    setSelectedTetkik((prev) => [...prev, { kodu, adi, brans: tetkikBrans }])
    setSearchQuery('')
    setIsDropdownOpen(false)
  }

  const removeTetkik = (kodu: string) => {
    setSelectedTetkik((prev) => prev.filter((t) => t.kodu !== kodu))
  }

  const handleSuggest = async () => {
    if (!reportSections || reportSections.length === 0) return
    setIsSuggesting(true)
    try {
      const sectionMap: Record<string, string> = {}
      for (const s of reportSections) {
        sectionMap[s.key] = s.content
      }
      const data = await apiClient.post<SUTSuggestResponse>('/api/v1/sut-tetkik/suggest', {
        report_sections: sectionMap,
        brans: brans || null,
      })
      // Drop low-confidence suggestions (likely false positives like
      // "Gaitada gizli kan aranması" matching "kan tahlili" by accident).
      // The LLM's confidence floor is 0.5; we surface only ≥0.85.
      // REPLACE the suggestion panel on every click — see ICD10Selector for
      // the rationale (avoids stale picks pinning above corrected ones).
      // selectedTetkik is stored separately and untouched by this reset.
      const next = data.suggestions
        .filter((s) => s.confidence >= SUT_MIN_CONFIDENCE)
        .sort((a, b) => b.confidence - a.confidence)
      setSuggestions(next)
      if (sessionId != null) storeSetSut(sessionId, next)
      setLastSuggestFingerprint(anamnesisFingerprint(reportSections))
    } catch {
      setSuggestions([])
      if (sessionId != null) storeSetSut(sessionId, [])
    } finally {
      setIsSuggesting(false)
    }
  }

  const handleSendToOpenEMR = async () => {
    if (!sessionId || selectedTetkik.length === 0) return
    setIsSendingToOpenEMR(true)
    setOpenEMRResult(null)
    try {
      const data = await apiClient.post<SUTOpenEMRSendResponse>(
        '/api/v1/sut-tetkik/send-to-openemr',
        {
          session_id: sessionId,
          tetkikler: selectedTetkik,
          notes: '',
        }
      )
      if (data.success) {
        const bransLabel = data.doctor_brans === 'dahiliye' ? t('admin_internalMed') : t('admin_ortho')
        const baseMsg = t('sut_sendSuccess', { count: data.sent_count, brans: bransLabel })
        const filteredMsg =
          data.filtered_count > 0
            ? ` — ${t('sut_sendFiltered', { count: data.filtered_count })}`
            : ''
        setOpenEMRResult({
          success: true,
          message: baseMsg + filteredMsg,
        })
      } else {
        setOpenEMRResult({
          success: false,
          message: data.error || t('report_sendFailed'),
        })
      }
    } catch (err) {
      setOpenEMRResult({
        success: false,
        message: err instanceof Error ? err.message : t('report_connectionError'),
      })
    } finally {
      setIsSendingToOpenEMR(false)
    }
  }

  const confidenceColor = (c: number) => {
    if (c >= 0.8) return 'text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/30'
    if (c >= 0.5) return 'text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/30'
    return 'text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900'
  }

  return (
    <div className="space-y-3">
      {/* AI Suggest Button */}
      {reportSections && reportSections.length > 0 && (
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => {
              if (canSuggest) void handleSuggest()
            }}
            disabled={isSuggesting}
            title={canSuggest ? t('sut_aiSuggest') : t('sut_suggestNoChange')}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium shadow-sm transition-colors disabled:opacity-50',
              canSuggest
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 cursor-not-allowed'
            )}
          >
            {isSuggesting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            {t('sut_aiSuggest')}
          </button>
          {!canSuggest && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {t('sut_suggestNoChange')}
            </p>
          )}
        </div>
      )}

      {/* AI Suggestions */}
      {suggestions.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{t('sut_aiSuggestions')}</p>
          {suggestions.map((s) => (
            <button
              key={s.kodu}
              type="button"
              onClick={() => addTetkik(s.kodu, s.adi, s.brans)}
              disabled={selectedTetkik.some((t) => t.kodu === s.kodu)}
              className={cn(
                'flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm transition-colors',
                selectedTetkik.some((t) => t.kodu === s.kodu)
                  ? 'border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 opacity-50'
                  : 'border-slate-200 dark:border-slate-700 hover:border-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/30'
              )}
            >
              <span>
                <span className="font-mono font-semibold text-blue-700 dark:text-blue-300">{s.kodu}</span>
                <span className="mx-1.5 text-slate-400 dark:text-slate-500">—</span>
                <span className="text-slate-700 dark:text-slate-200">{s.adi}</span>
              </span>
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-xs font-medium',
                  confidenceColor(s.confidence)
                )}
              >
                %{Math.round(s.confidence * 100)}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Search Input */}
      <div className="relative" ref={dropdownRef}>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setIsDropdownOpen(true)
            }}
            onFocus={() => searchQuery.length >= 2 && setIsDropdownOpen(true)}
            placeholder={t('sut_searchPlaceholder')}
            className="w-full rounded-lg border border-slate-200 dark:border-slate-700 py-2 pl-9 pr-3 text-sm text-slate-700 dark:text-slate-200 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          />
          {isLoading && (
            <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-slate-400 dark:text-slate-500" />
          )}
        </div>

        {/* Dropdown Results */}
        {isDropdownOpen && results.length > 0 && (
          <div className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg">
            {results.map((r) => (
              <button
                key={r.kodu}
                type="button"
                onClick={() => addTetkik(r.kodu, r.adi, r.brans)}
                disabled={selectedTetkik.some((t) => t.kodu === r.kodu)}
                className={cn(
                  'flex w-full items-start gap-2 px-3 py-2 text-left text-sm transition-colors',
                  selectedTetkik.some((t) => t.kodu === r.kodu)
                    ? 'bg-emerald-50 dark:bg-emerald-900/30 opacity-50'
                    : 'hover:bg-blue-50 dark:hover:bg-blue-900/30'
                )}
              >
                <span className="shrink-0 font-mono font-semibold text-blue-700 dark:text-blue-300">
                  {r.kodu}
                </span>
                <span className="text-slate-700 dark:text-slate-200">{r.adi}</span>
              </button>
            ))}
          </div>
        )}

        {isDropdownOpen && searchQuery.length >= 2 && results.length === 0 && !isLoading && (
          <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-4 text-center text-sm text-slate-500 dark:text-slate-400 shadow-lg">
            {t('sut_noResults')}
          </div>
        )}
      </div>

      {/* Selected Tetkik */}
      {selectedTetkik.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{t('sut_selectedTests')}</p>
          {selectedTetkik.map((t) => (
            <div
              key={t.kodu}
              className="flex items-center justify-between rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 px-3 py-2"
            >
              <span className="text-sm">
                <span className="font-mono font-semibold text-emerald-700 dark:text-emerald-300">{t.kodu}</span>
                <span className="mx-1.5 text-slate-400 dark:text-slate-500">—</span>
                <span className="text-slate-700 dark:text-slate-200">{t.adi}</span>
                <span className="ml-1.5 text-xs text-slate-400 dark:text-slate-500">[{t.brans}]</span>
              </span>
              <button
                type="button"
                onClick={() => removeTetkik(t.kodu)}
                className="rounded p-0.5 text-slate-400 dark:text-slate-500 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-500 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* OpenEMR Send Button */}
      {selectedTetkik.length > 0 && sessionId && user?.brans && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={handleSendToOpenEMR}
            disabled={isSendingToOpenEMR}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            {isSendingToOpenEMR ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            {t('sut_sendToOpenEMR', { brans: user.brans === 'dahiliye' ? t('admin_internalMed') : t('admin_ortho') })}
          </button>

          {openEMRResult && (
            <div
              className={cn(
                'flex items-start gap-2 rounded-lg border px-3 py-2 text-xs',
                openEMRResult.success
                  ? 'border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                  : 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'
              )}
            >
              {openEMRResult.success ? (
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              ) : (
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              )}
              <span>{openEMRResult.message}</span>
            </div>
          )}
        </div>
      )}

      {selectedTetkik.length === 0 && suggestions.length === 0 && (
        <p className="text-xs text-slate-400 dark:text-slate-500 italic">
          {t('sut_noTestSelected')}
        </p>
      )}
    </div>
  )
}
