import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  Clock,
  User,
  Stethoscope,
  Loader2,
  RefreshCw,
  Mic,
} from 'lucide-react'
import { cn } from '../lib/utils'
import { apiClient } from '../services/apiClient'
import { useAuthStore } from '../stores/authStore'
import { useUIStore } from '../stores/uiStore'
import { useT } from '../hooks/useT'

interface Appointment {
  id: number
  title: string
  date: string
  start_time: string
  end_time: string
  duration_seconds: number
  provider_id: number
  provider_name: string
  provider_username: string
  patient_id: string
  patient_name: string
  patient_ext_id: string
  status: string
  category_name: string
  category_color: string
  reason: string
}

interface AppointmentListResponse {
  appointments: Appointment[]
  total: number
  date: string
  filtered_by: string
}

function formatTime(time: string): string {
  return time.slice(0, 5)
}

function getToday(): string {
  const d = new Date()
  return d.toISOString().split('T')[0]
}

function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr + 'T00:00:00')
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
}

function getWeekDates(dateStr: string): string[] {
  const d = new Date(dateStr + 'T00:00:00')
  const day = d.getDay()
  const mondayOffset = day === 0 ? -6 : 1 - day
  const monday = new Date(d)
  monday.setDate(d.getDate() + mondayOffset)

  const dates: string[] = []
  for (let i = 0; i < 7; i++) {
    const curr = new Date(monday)
    curr.setDate(monday.getDate() + i)
    dates.push(curr.toISOString().split('T')[0])
  }
  return dates
}

function getDayNum(dateStr: string): number {
  return new Date(dateStr + 'T00:00:00').getDate()
}

export function CalendarPage(): React.JSX.Element {
  const [selectedDate, setSelectedDate] = useState(getToday)
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [loading, setLoading] = useState(true)
  const [filteredBy, setFilteredBy] = useState('')
  const user = useAuthStore((s) => s.user)
  const locale = useUIStore((s) => s.locale)
  const navigate = useNavigate()
  const t = useT()

  const weekDates = getWeekDates(selectedDate)
  const intlLocale = locale === 'tr' ? 'tr-TR' : 'en-US'

  const formatDateLocale = (dateStr: string): string => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString(intlLocale, {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  }

  const getShortDay = (dateStr: string): string => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString(intlLocale, { weekday: 'short' })
  }

  const fetchAppointments = useCallback(async (date: string) => {
    setLoading(true)
    try {
      const data = await apiClient.get<AppointmentListResponse>(
        `/api/v1/appointments?appointment_date=${date}`
      )
      setAppointments(data.appointments)
      setFilteredBy(data.filtered_by)
    } catch {
      setAppointments([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchAppointments(selectedDate)
  }, [selectedDate, fetchAppointments])

  const isToday = selectedDate === getToday()

  return (
    <div className="flex-1 overflow-auto bg-slate-50 dark:bg-slate-900">
      <div className="mx-auto max-w-3xl p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CalendarIcon className="h-7 w-7 text-blue-600" />
            <div>
              <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">{t('cal_title')}</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {user?.role === 'admin'
                  ? t('cal_subtitle_all')
                  : t('cal_subtitle_doctor', { name: user?.display_name ?? '' })}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!isToday && (
              <button
                onClick={() => setSelectedDate(getToday())}
                className="rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50  transition-colors"
              >
                {t('cal_today')}
              </button>
            )}
            <button
              onClick={() => void fetchAppointments(selectedDate)}
              className="rounded-lg border border-slate-300 dark:border-slate-600 p-2 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50  transition-colors"
              title={t('cal_refresh')}
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Week Navigation */}
        <div className="rounded-xl bg-white dark:bg-slate-800 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60 p-3">
          <div className="flex items-center justify-between mb-3">
            <button
              onClick={() => setSelectedDate(addDays(selectedDate, -7))}
              className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700  hover:text-slate-600 dark:hover:text-slate-200  transition-colors"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              {formatDateLocale(selectedDate)}
            </span>
            <button
              onClick={() => setSelectedDate(addDays(selectedDate, 7))}
              className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700  hover:text-slate-600 dark:hover:text-slate-200  transition-colors"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
          <div className="grid grid-cols-7 gap-1">
            {weekDates.map((d) => {
              const isSelected = d === selectedDate
              const isTodayDate = d === getToday()
              return (
                <button
                  key={d}
                  onClick={() => setSelectedDate(d)}
                  className={cn(
                    'flex flex-col items-center rounded-lg py-2 text-xs transition-colors',
                    isSelected
                      ? 'bg-blue-600 text-white'
                      : isTodayDate
                        ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-100'
                        : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 '
                  )}
                >
                  <span className="font-medium">{getShortDay(d)}</span>
                  <span className={cn('mt-0.5 text-lg font-bold', isSelected ? 'text-white' : '')}>
                    {getDayNum(d)}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Filter Badge */}
        {filteredBy && filteredBy !== 'tumu' && (
          <div className="flex items-center gap-2">
            <Stethoscope className="h-4 w-4 text-slate-400 dark:text-slate-500" />
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {t('cal_filter')} <span className="font-medium text-slate-700 dark:text-slate-200">
                {filteredBy === 'dahiliye' ? t('header_internalMed') : t('header_ortho')}
              </span>
            </span>
          </div>
        )}

        {/* Appointment List */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400 dark:text-slate-500" />
          </div>
        ) : appointments.length === 0 ? (
          <div className="rounded-xl bg-white dark:bg-slate-800 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60 p-12 text-center">
            <CalendarIcon className="mx-auto h-10 w-10 text-slate-300 dark:text-slate-600 mb-3" />
            <p className="text-sm text-slate-500 dark:text-slate-400">{t('cal_noAppts')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {appointments.map((appt) => (
              <div
                key={appt.id}
                className="rounded-xl bg-white dark:bg-slate-800 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60 overflow-hidden"
              >
                <div className="flex">
                  {/* Color bar */}
                  <div
                    className="w-1.5 shrink-0"
                    style={{ backgroundColor: appt.category_color || '#94a3b8' }}
                  />
                  <div className="flex-1 px-4 py-3">
                    <div className="flex items-start justify-between">
                      <div className="space-y-1">
                        {/* Patient */}
                        <div className="flex items-center gap-2">
                          <User className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                          <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                            {appt.patient_name || t('cal_noPatient')}
                          </span>
                        </div>
                        {/* Reason / Complaint from reception */}
                        {appt.reason && (
                          <p className="ml-6 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/30 rounded px-2 py-1 inline-block">
                            {t('cal_complaint')} {appt.reason}
                          </p>
                        )}
                        {/* Provider (admin sees this) */}
                        {user?.role === 'admin' && (
                          <div className="flex items-center gap-2">
                            <Stethoscope className="h-3.5 w-3.5 text-blue-400" />
                            <span className="text-xs text-blue-600 font-medium">
                              Dr. {appt.provider_name}
                            </span>
                          </div>
                        )}
                        {/* Category */}
                        <span
                          className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium"
                          style={{
                            backgroundColor: appt.category_color + '33',
                            color: appt.category_color === '#dee2e6' ? '#6b7280' : '#374151',
                          }}
                        >
                          {appt.category_name}
                        </span>
                      </div>
                      {/* Time + Action */}
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                          <Clock className="h-4 w-4" />
                          <span className="text-sm font-mono font-medium">
                            {formatTime(appt.start_time)}
                            {appt.end_time !== appt.start_time && (
                              <> — {formatTime(appt.end_time)}</>
                            )}
                          </span>
                        </div>
                        {(user?.role === 'admin' || appt.provider_username === user?.username) && (
                          <button
                            onClick={() => {
                              const params = new URLSearchParams({
                                patient_id: appt.patient_ext_id || appt.patient_id,
                                patient_name: appt.patient_name,
                                provider: appt.provider_name,
                                appointment_id: String(appt.id),
                              })
                              navigate(`/session/new?${params.toString()}`)
                            }}
                            className="flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 transition-colors"
                          >
                            <Mic className="h-3.5 w-3.5" />
                            {t('cal_startRecording')}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Summary */}
        {!loading && appointments.length > 0 && (
          <p className="text-xs text-slate-400 dark:text-slate-500 text-center">
            {t('cal_total', { count: appointments.length })}
          </p>
        )}
      </div>
    </div>
  )
}
