import { useState, useRef, useEffect } from 'react'
import { Search, Sparkles, X, Loader2, Send, CheckCircle2, AlertCircle } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useSutTetkikSearch } from '../../hooks/useSutTetkikSearch'
import { apiClient } from '../../services/apiClient'
import { useAuthStore } from '../../stores/authStore'
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

export function SutTetkikSelector({ value, reportSections, brans: bransProp, sessionId, onChange }: SutTetkikSelectorProps) {
  const parsed = parseExistingTetkik(value)
  const [selectedTetkik, setSelectedTetkik] = useState<SUTConfirmedTetkik[]>(() =>
    parsed.filter((p) => p.confidence === undefined).map(({ confidence: _, ...rest }) => rest)
  )
  const [searchQuery, setSearchQuery] = useState('')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [suggestions, setSuggestions] = useState<SUTSuggestion[]>(() =>
    parsed
      .filter((p) => p.confidence !== undefined)
      .map((p) => ({
        kodu: p.kodu,
        adi: p.adi,
        brans: p.brans,
        confidence: p.confidence ?? 0.5,
        reasoning: '',
      }))
      .sort((a, b) => b.confidence - a.confidence)
  )
  const [isSuggesting, setIsSuggesting] = useState(false)
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
    console.log('[SUT] handleSuggest called, reportSections:', reportSections?.length)
    if (!reportSections || reportSections.length === 0) {
      console.log('[SUT] No reportSections, returning')
      return
    }
    setIsSuggesting(true)
    try {
      const sectionMap: Record<string, string> = {}
      for (const s of reportSections) {
        sectionMap[s.key] = s.content
      }
      console.log('[SUT] Sending request with sections:', Object.keys(sectionMap).length)
      const data = await apiClient.post<SUTSuggestResponse>('/api/v1/sut-tetkik/suggest', {
        report_sections: sectionMap,
        brans: brans || null,
      })
      console.log('[SUT] Got response:', data.suggestions.length, 'suggestions')
      setSuggestions([...data.suggestions].sort((a, b) => b.confidence - a.confidence))
    } catch (err) {
      console.error('[SUT] Error:', err)
      setSuggestions([])
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
        const bransLabel = data.doctor_brans === 'dahiliye' ? 'Dahiliye' : 'Ortopedi'
        setOpenEMRResult({
          success: true,
          message: `${data.sent_count} tetkik OpenEMR'e gönderildi (${bransLabel})${
            data.filtered_count > 0
              ? ` — ${data.filtered_count} tetkik branş uyumsuzluğu nedeniyle filtrelendi`
              : ''
          }`,
        })
      } else {
        setOpenEMRResult({
          success: false,
          message: data.error || 'OpenEMR gönderimi başarısız',
        })
      }
    } catch (err) {
      console.error('[SUT] OpenEMR send error:', err)
      setOpenEMRResult({
        success: false,
        message: 'OpenEMR bağlantı hatası',
      })
    } finally {
      setIsSendingToOpenEMR(false)
    }
  }

  const confidenceColor = (c: number) => {
    if (c >= 0.8) return 'text-emerald-700 bg-emerald-50'
    if (c >= 0.5) return 'text-amber-700 bg-amber-50'
    return 'text-slate-500 bg-slate-50'
  }

  return (
    <div className="space-y-3">
      {/* AI Suggest Button */}
      {reportSections && reportSections.length > 0 && (
        <button
          type="button"
          onClick={handleSuggest}
          disabled={isSuggesting}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {isSuggesting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          AI ile Tetkik Öner
        </button>
      )}

      {/* AI Suggestions */}
      {suggestions.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-slate-500">AI Tetkik Önerileri:</p>
          {suggestions.map((s) => (
            <button
              key={s.kodu}
              type="button"
              onClick={() => addTetkik(s.kodu, s.adi, s.brans)}
              disabled={selectedTetkik.some((t) => t.kodu === s.kodu)}
              className={cn(
                'flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm transition-colors',
                selectedTetkik.some((t) => t.kodu === s.kodu)
                  ? 'border-emerald-200 bg-emerald-50 opacity-50'
                  : 'border-slate-200 hover:border-blue-300 hover:bg-blue-50'
              )}
            >
              <span>
                <span className="font-mono font-semibold text-blue-700">{s.kodu}</span>
                <span className="mx-1.5 text-slate-400">—</span>
                <span className="text-slate-700">{s.adi}</span>
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
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setIsDropdownOpen(true)
            }}
            onFocus={() => searchQuery.length >= 2 && setIsDropdownOpen(true)}
            placeholder="SÜT kodu veya tetkik adı yazın..."
            className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          />
          {isLoading && (
            <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-slate-400" />
          )}
        </div>

        {/* Dropdown Results */}
        {isDropdownOpen && results.length > 0 && (
          <div className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
            {results.map((r) => (
              <button
                key={r.kodu}
                type="button"
                onClick={() => addTetkik(r.kodu, r.adi, r.brans)}
                disabled={selectedTetkik.some((t) => t.kodu === r.kodu)}
                className={cn(
                  'flex w-full items-start gap-2 px-3 py-2 text-left text-sm transition-colors',
                  selectedTetkik.some((t) => t.kodu === r.kodu)
                    ? 'bg-emerald-50 opacity-50'
                    : 'hover:bg-blue-50'
                )}
              >
                <span className="shrink-0 font-mono font-semibold text-blue-700">
                  {r.kodu}
                </span>
                <span className="text-slate-700">{r.adi}</span>
              </button>
            ))}
          </div>
        )}

        {isDropdownOpen && searchQuery.length >= 2 && results.length === 0 && !isLoading && (
          <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-4 text-center text-sm text-slate-500 shadow-lg">
            Sonuç bulunamadı
          </div>
        )}
      </div>

      {/* Selected Tetkik */}
      {selectedTetkik.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-slate-500">Seçilen tetkikler:</p>
          {selectedTetkik.map((t) => (
            <div
              key={t.kodu}
              className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2"
            >
              <span className="text-sm">
                <span className="font-mono font-semibold text-emerald-700">{t.kodu}</span>
                <span className="mx-1.5 text-slate-400">—</span>
                <span className="text-slate-700">{t.adi}</span>
                <span className="ml-1.5 text-xs text-slate-400">[{t.brans}]</span>
              </span>
              <button
                type="button"
                onClick={() => removeTetkik(t.kodu)}
                className="rounded p-0.5 text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors"
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
            OpenEMR'e Gönder ({user.brans === 'dahiliye' ? 'Dahiliye' : 'Ortopedi'})
          </button>

          {openEMRResult && (
            <div
              className={cn(
                'flex items-start gap-2 rounded-lg border px-3 py-2 text-xs',
                openEMRResult.success
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-red-200 bg-red-50 text-red-700'
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
        <p className="text-xs text-slate-400 italic">
          Tetkik seçilmedi. Arama yapın veya AI ile öneri alın.
        </p>
      )}
    </div>
  )
}
