import { useState, useRef, useEffect } from 'react'
import { Search, Sparkles, X, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useICD10Search } from '../../hooks/useICD10Search'
import { useT } from '../../hooks/useT'
import { apiClient } from '../../services/apiClient'
import { useReportSuggestionStore } from '../../stores/reportSuggestionStore'
import type { ICD10ConfirmedCode, ICD10Suggestion, ICD10SuggestResponse } from '../../types/icd10'

interface ReportSectionData {
  key: string
  content: string
}

interface ICD10SelectorProps {
  value: string
  reportSections?: ReportSectionData[]
  sessionId?: number
  onChange: (formatted: string) => void
}

interface ParsedCode extends ICD10ConfirmedCode {
  confidence?: number
}

function parseExistingCodes(value: string): ParsedCode[] {
  if (!value || value === 'BELIRTILMEDI') return []
  const codes: ParsedCode[] = []
  const lines = value.split('\n').filter((l) => l.trim())
  for (const line of lines) {
    const match = line.match(
      /^\(([A-Z0-9.]+)\)\s*-\s*(.+?)(?:\s*\((Ön Tanı|On Tanı|Kesin Tanı|Ön Tani|On Tani|Kesin Tani)\))?(?:\s*\[%(\d+)\])?$/
    )
    if (match) {
      const taniTipi = match[3]?.toLowerCase().includes('kesin') ? 'kesin_tani' as const : 'on_tani' as const
      const confidence = match[4] ? parseInt(match[4], 10) / 100 : undefined
      codes.push({ icd_kodu: match[1], tani: match[2].trim(), tani_tipi: taniTipi, confidence })
    }
  }
  return codes
}

function formatCodes(codes: ICD10ConfirmedCode[]): string {
  if (codes.length === 0) return ''
  return codes
    .map((c) => {
      const tipi = c.tani_tipi === 'kesin_tani' ? 'Kesin Tanı' : 'Ön Tanı'
      return `(${c.icd_kodu}) - ${c.tani} (${tipi})`
    })
    .join('\n')
}

// Anamnez alanlarının (icd10/sut bölümleri hariç) parmak izi — "AI Öner"
// butonunun yalnızca anamnez metni değiştiğinde aktif olması için kullanılır.
function anamnesisFingerprint(sections?: ReportSectionData[]): string {
  if (!sections) return ''
  return sections
    .filter((s) => s.key !== 'icd10_list' && s.key !== 'sut_tetkik_list')
    .map((s) => s.content)
    .join('')
}

export function ICD10Selector({ value, reportSections, sessionId, onChange }: ICD10SelectorProps) {
  const t = useT()
  const storeSetIcd = useReportSuggestionStore((s) => s.setIcd)
  const parsed = parseExistingCodes(value)
  const [selectedCodes, setSelectedCodes] = useState<ICD10ConfirmedCode[]>(() =>
    parsed.filter((p) => p.confidence === undefined).map(({ confidence: _, ...rest }) => rest)
  )
  const [searchQuery, setSearchQuery] = useState('')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  // Same threshold used in handleSuggest below — apply here too so reports
  // that were saved before the threshold existed don't surface stale
  // low-confidence picks.
  const ICD_MIN_CONFIDENCE = 0.5
  const [suggestions, setSuggestions] = useState<ICD10Suggestion[]>(() => {
    // "Geri" ile sayfadan çıkıp dönülünce öneriler kaybolmasın: önce session
    // bazlı önbelleğe bak, yoksa kayıtlı içerikten ayrıştır.
    const cached =
      sessionId != null ? useReportSuggestionStore.getState().icd[sessionId] : undefined
    if (cached) return cached
    return parsed
      .filter((p) => p.confidence !== undefined && p.confidence >= ICD_MIN_CONFIDENCE)
      .map((p) => ({
        icd_kodu: p.icd_kodu,
        tani: p.tani,
        confidence: p.confidence ?? 0.5,
        reasoning: '',
        source: (p as ICD10Suggestion).source,
      }))
      .sort((a, b) => b.confidence - a.confidence)
  })
  const [isSuggesting, setIsSuggesting] = useState(false)
  // Son öneri anındaki anamnez parmak izi. Anamnez değişmediyse "AI Öner"
  // pasif olur — aynı metinle tekrar öneri istemek anlamsız.
  const [lastSuggestFingerprint, setLastSuggestFingerprint] = useState<string>(
    () => anamnesisFingerprint(reportSections),
  )
  // Uyarı yalnızca pasif butona tıklanınca gösterilir — sürekli durmaz.
  const [showNoChangeHint, setShowNoChangeHint] = useState(false)
  const canSuggest =
    suggestions.length === 0 ||
    anamnesisFingerprint(reportSections) !== lastSuggestFingerprint
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { results, isLoading } = useICD10Search(searchQuery)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Sync selectedCodes -> formatted string, but only when codes actually change.
  // We use a ref for onChange to avoid triggering the effect when the parent
  // re-renders with a new callback reference (e.g. after approve sets status).
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const isInitialMount = useRef(true)
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false
      return
    }
    onChangeRef.current(formatCodes(selectedCodes))
  }, [selectedCodes])

  // Kayıt sonrası otomatik gelen öneriler ilk yüklemede bölüm içeriğinden
  // ayrıştırılır. Bunları da bir kez store'a yaz ki içerik sonradan
  // (kod ekleme / kaydetme ile) değişse bile "geri" sonrası korunsunlar.
  useEffect(() => {
    if (
      sessionId != null &&
      suggestions.length > 0 &&
      useReportSuggestionStore.getState().icd[sessionId] === undefined
    ) {
      storeSetIcd(sessionId, suggestions)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const addCode = (kodu: string, tani: string) => {
    if (selectedCodes.some((c) => c.icd_kodu === kodu)) return
    setSelectedCodes((prev) => [...prev, { icd_kodu: kodu, tani, tani_tipi: 'on_tani' }])
    setSearchQuery('')
    setIsDropdownOpen(false)
  }

  const removeCode = (kodu: string) => {
    setSelectedCodes((prev) => prev.filter((c) => c.icd_kodu !== kodu))
  }

  const toggleTaniTipi = (kodu: string) => {
    setSelectedCodes((prev) =>
      prev.map((c) =>
        c.icd_kodu === kodu
          ? { ...c, tani_tipi: c.tani_tipi === 'on_tani' ? 'kesin_tani' : 'on_tani' }
          : c
      )
    )
  }

  const handleSuggest = async () => {
    if (!reportSections || reportSections.length === 0) return
    setIsSuggesting(true)
    try {
      const sectionMap: Record<string, string> = {}
      for (const s of reportSections) {
        sectionMap[s.key] = s.content
      }
      const data = await apiClient.post<ICD10SuggestResponse>('/api/v1/icd10/suggest', {
        report_sections: sectionMap,
      })
      // Hide low-confidence suggestions. ICD-10 retrieval can return loosely-
      // related codes (e.g. I20 angina alongside E05.9 thyrotoxicosis when the
      // patient only has palpitations). The LLM flags those with <0.7
      // confidence; surfacing them clutters the UI without adding value —
      // the doctor can search for them manually if needed.
      // REPLACE the suggestion panel on every "AI Öner" click. Earlier we
      // tried merging old + new but that pinned outdated picks (e.g. J44.0
      // from a pre-prompt-fix run kept appearing above the corrected J44.9).
      // selectedCodes (codes the user has explicitly added to the report)
      // are stored separately and unaffected by this reset.
      const next = data.suggestions
        .filter((s) => s.confidence >= ICD_MIN_CONFIDENCE)
        .sort((a, b) => b.confidence - a.confidence)
      setSuggestions(next)
      if (sessionId != null) storeSetIcd(sessionId, next)
      setLastSuggestFingerprint(anamnesisFingerprint(reportSections))
    } catch {
      setSuggestions([])
      if (sessionId != null) storeSetIcd(sessionId, [])
    } finally {
      setIsSuggesting(false)
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
              if (canSuggest) {
                void handleSuggest()
              } else {
                setShowNoChangeHint(true)
                setTimeout(() => setShowNoChangeHint(false), 5000)
              }
            }}
            disabled={isSuggesting}
            title={canSuggest ? t('icd10_aiSuggest') : t('icd10_suggestNoChange')}
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
            {t('icd10_aiSuggest')}
          </button>
          {showNoChangeHint && !canSuggest && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {t('icd10_suggestNoChange')}
            </p>
          )}
        </div>
      )}

      {/* AI Suggestions */}
      {suggestions.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{t('icd10_aiSuggestions')}</p>
          {suggestions.map((s) => (
            <button
              key={s.icd_kodu}
              type="button"
              onClick={() => addCode(s.icd_kodu, s.tani)}
              disabled={selectedCodes.some((c) => c.icd_kodu === s.icd_kodu)}
              className={cn(
                'flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm transition-colors',
                selectedCodes.some((c) => c.icd_kodu === s.icd_kodu)
                  ? 'border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 opacity-50'
                  : 'border-slate-200 dark:border-slate-700 hover:border-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/30'
              )}
            >
              <span className="flex items-center gap-2">
                <span className="font-mono font-semibold text-blue-700 dark:text-blue-300">{s.icd_kodu}</span>
                <span className="text-slate-400 dark:text-slate-500">—</span>
                <span className="text-slate-700 dark:text-slate-200">{s.tani}</span>
                {s.source === 'semptom' && (
                  <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                    semptom
                  </span>
                )}
                {s.source === 'cikarim' && (
                  <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200">
                    çıkarım
                  </span>
                )}
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
            placeholder={t('icd10_searchPlaceholder')}
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
                key={r.icd_kodu}
                type="button"
                onClick={() => addCode(r.icd_kodu, r.tani)}
                disabled={selectedCodes.some((c) => c.icd_kodu === r.icd_kodu)}
                className={cn(
                  'flex w-full items-start gap-2 px-3 py-2 text-left text-sm transition-colors',
                  selectedCodes.some((c) => c.icd_kodu === r.icd_kodu)
                    ? 'bg-emerald-50 dark:bg-emerald-900/30 opacity-50'
                    : 'hover:bg-blue-50 dark:hover:bg-blue-900/30'
                )}
              >
                <span className="shrink-0 font-mono font-semibold text-blue-700 dark:text-blue-300">
                  {r.icd_kodu}
                </span>
                <span className="text-slate-700 dark:text-slate-200">{r.tani}</span>
              </button>
            ))}
          </div>
        )}

        {isDropdownOpen && searchQuery.length >= 2 && results.length === 0 && !isLoading && (
          <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-4 text-center text-sm text-slate-500 dark:text-slate-400 shadow-lg">
            {t('icd10_noResults')}
          </div>
        )}
      </div>

      {/* Selected Codes */}
      {selectedCodes.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{t('icd10_selected')}</p>
          {selectedCodes.map((c) => (
            <div
              key={c.icd_kodu}
              className="flex items-center justify-between rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 px-3 py-2"
            >
              <span className="text-sm">
                <span className="font-mono font-semibold text-emerald-700 dark:text-emerald-300">{c.icd_kodu}</span>
                <span className="mx-1.5 text-slate-400 dark:text-slate-500">—</span>
                <span className="text-slate-700 dark:text-slate-200">{c.tani}</span>
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => toggleTaniTipi(c.icd_kodu)}
                  className={cn(
                    'rounded-full px-2 py-0.5 text-xs font-medium transition-colors',
                    c.tani_tipi === 'kesin_tani'
                      ? 'bg-emerald-600 text-white'
                      : 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300'
                  )}
                >
                  {c.tani_tipi === 'kesin_tani' ? t('icd10_definite') : t('icd10_preliminary')}
                </button>
                <button
                  type="button"
                  onClick={() => removeCode(c.icd_kodu)}
                  className="rounded p-0.5 text-slate-400 dark:text-slate-500 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-500 transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedCodes.length === 0 && suggestions.length === 0 && (
        <p className="text-xs text-slate-400 dark:text-slate-500 italic">
          {t('icd10_emptyHint')}
        </p>
      )}
    </div>
  )
}
