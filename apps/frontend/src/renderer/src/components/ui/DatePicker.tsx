import { useState, useRef, useEffect, useMemo } from 'react'
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'
import { useT } from '../../hooks/useT'
import { cn } from '../../lib/utils'

interface DatePickerProps {
  value: string  // ISO string YYYY-MM-DD or empty
  onChange: (value: string) => void
  placeholder?: string
  id?: string
  className?: string
}

function pad2(n: number): string {
  return n.toString().padStart(2, '0')
}

function toISO(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

function parseISO(s: string): Date | null {
  if (!s) return null
  const [y, m, d] = s.split('-').map(Number)
  if (!y || !m || !d) return null
  return new Date(y, m - 1, d)
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1)
}

export function DatePicker({
  value,
  onChange,
  placeholder,
  id,
  className,
}: DatePickerProps): React.JSX.Element {
  const locale = useUIStore((s) => s.locale)
  const intlLocale = locale === 'tr' ? 'tr-TR' : 'en-US'
  const t = useT()

  const [open, setOpen] = useState(false)
  const [viewMonth, setViewMonth] = useState<Date>(() => parseISO(value) ?? new Date())
  const containerRef = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent): void => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // Sync viewMonth when value changes externally
  useEffect(() => {
    const parsed = parseISO(value)
    if (parsed) setViewMonth(startOfMonth(parsed))
  }, [value])

  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(intlLocale, { year: 'numeric', month: 'short', day: 'numeric' }),
    [intlLocale],
  )
  const monthFormatter = useMemo(
    () => new Intl.DateTimeFormat(intlLocale, { year: 'numeric', month: 'long' }),
    [intlLocale],
  )
  const weekdayShortFormatter = useMemo(
    () => new Intl.DateTimeFormat(intlLocale, { weekday: 'short' }),
    [intlLocale],
  )

  // Build day names starting Monday (0 = Mon ... 6 = Sun)
  const dayNames = useMemo(() => {
    // Pick a Monday: 2024-01-01 was Monday
    const base = new Date(2024, 0, 1)
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(base)
      d.setDate(base.getDate() + i)
      return weekdayShortFormatter.format(d)
    })
  }, [weekdayShortFormatter])

  // Build the days grid for viewMonth — 6 rows x 7 cols
  const grid = useMemo(() => {
    const first = startOfMonth(viewMonth)
    // JS getDay: Sun=0..Sat=6 → convert to Mon=0..Sun=6
    const firstDow = (first.getDay() + 6) % 7
    const cells: Date[] = []
    const start = new Date(first)
    start.setDate(first.getDate() - firstDow)
    for (let i = 0; i < 42; i++) {
      const d = new Date(start)
      d.setDate(start.getDate() + i)
      cells.push(d)
    }
    return cells
  }, [viewMonth])

  const selected = parseISO(value)
  const today = new Date()
  const isSameDay = (a: Date, b: Date | null): boolean =>
    !!b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()

  const displayValue = selected ? dateFormatter.format(selected) : ''
  const placeholderText = placeholder ?? t('datepicker_placeholder')

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      <button
        id={id}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-slate-100 hover:border-blue-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 min-w-[140px]"
      >
        <CalendarIcon className="h-4 w-4 text-slate-400 dark:text-slate-500 shrink-0" />
        <span className={cn('flex-1 text-left', !displayValue && 'text-slate-400 dark:text-slate-500')}>
          {displayValue || placeholderText}
        </span>
        {value && (
          <X
            className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 hover:text-red-500 shrink-0"
            onClick={(e) => {
              e.stopPropagation()
              onChange('')
            }}
          />
        )}
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 shadow-lg w-[260px]">
          <div className="flex items-center justify-between mb-2">
            <button
              type="button"
              onClick={() => setViewMonth(addMonths(viewMonth, -1))}
              className="rounded p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-200 capitalize">
              {monthFormatter.format(viewMonth)}
            </span>
            <button
              type="button"
              onClick={() => setViewMonth(addMonths(viewMonth, 1))}
              className="rounded p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-7 gap-0.5 mb-1">
            {dayNames.map((name) => (
              <div
                key={name}
                className="text-center text-[10px] font-medium uppercase text-slate-400 dark:text-slate-500 py-1"
              >
                {name}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-0.5">
            {grid.map((d) => {
              const inMonth = d.getMonth() === viewMonth.getMonth()
              const isToday = isSameDay(d, today)
              const isSelected = isSameDay(d, selected)
              return (
                <button
                  key={d.toISOString()}
                  type="button"
                  onClick={() => {
                    onChange(toISO(d))
                    setOpen(false)
                  }}
                  className={cn(
                    'aspect-square text-xs rounded-md transition-colors',
                    !inMonth && 'text-slate-300 dark:text-slate-600',
                    inMonth && !isSelected && 'text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700',
                    isToday && !isSelected && 'ring-1 ring-blue-400 dark:ring-blue-500',
                    isSelected && 'bg-blue-600 text-white font-semibold',
                  )}
                >
                  {d.getDate()}
                </button>
              )
            })}
          </div>

          <div className="flex justify-between mt-3 pt-2 border-t border-slate-100 dark:border-slate-700">
            <button
              type="button"
              onClick={() => {
                onChange(toISO(today))
                setViewMonth(startOfMonth(today))
                setOpen(false)
              }}
              className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700"
            >
              {t('datepicker_today')}
            </button>
            {value && (
              <button
                type="button"
                onClick={() => {
                  onChange('')
                  setOpen(false)
                }}
                className="text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-red-500"
              >
                {t('datepicker_clear')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
