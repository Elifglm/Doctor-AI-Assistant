import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Mic, Loader2, AlertCircle, History } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useCreateSession } from '../hooks/useSession'
import { useT } from '../hooks/useT'
import { KvkkConsentModal } from '../components/ui/KvkkConsentModal'
import { apiClient } from '../services/apiClient'
import type { VisitType } from '../types/session'

interface RecordingsTestModeResponse {
  keep_recordings: boolean
}

interface RecordingItem {
  path: string
  filename: string
  session_id: number | null
  timestamp: number | null
  size_bytes: number
}

interface RecordingListResponse {
  patient_id: string
  items: RecordingItem[]
}

export function PreSessionPage(): React.JSX.Element {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const user = useAuthStore((s) => s.user)
  const createSession = useCreateSession()
  const t = useT()

  // Pre-fill from calendar appointment query params
  const appointmentPatientId = searchParams.get('patient_id') ?? ''
  const appointmentPatientName = searchParams.get('patient_name') ?? ''
  const appointmentProvider = searchParams.get('provider') ?? ''
  const appointmentId = searchParams.get('appointment_id') ?? ''

  // If no appointment data, redirect to calendar
  const hasAppointment = Boolean(appointmentPatientId && appointmentPatientName)

  const visitType: VisitType = 'ilk_muayene'
  const [kvkkConsent, setKvkkConsent] = useState(false)
  const [kvkkModalOpen, setKvkkModalOpen] = useState(false)
  const [selectedRecordingPath, setSelectedRecordingPath] = useState<string | null>(null)

  const doctorName = appointmentProvider || user?.display_name || ''

  // Test modu yalnızca admin tarafından açılabilir; kayıt seçici sadece açıkken
  // ve hasta için mevcut WAV varsa gösterilir.
  const { data: testMode } = useQuery<RecordingsTestModeResponse>({
    queryKey: ['recordings-test-mode'],
    queryFn: () =>
      apiClient.get<RecordingsTestModeResponse>('/api/v1/recordings/test-mode'),
    enabled: hasAppointment,
  })

  const { data: recordings } = useQuery<RecordingListResponse>({
    queryKey: ['recordings', appointmentPatientId],
    queryFn: () =>
      apiClient.get<RecordingListResponse>(
        `/api/v1/recordings/by-patient/${encodeURIComponent(appointmentPatientId)}`
      ),
    enabled: Boolean(testMode?.keep_recordings) && Boolean(appointmentPatientId),
  })

  const recordingItems = recordings?.items ?? []
  const showRecordingPicker =
    Boolean(testMode?.keep_recordings) && recordingItems.length > 0

  const handleSubmit = (e: FormEvent<HTMLFormElement>): void => {
    e.preventDefault()

    if (!kvkkConsent) return

    createSession.mutate(
      {
        patient_id: appointmentPatientId,
        patient_name: appointmentPatientName,
        visit_type: visitType,
        doctor_name: doctorName,
        kvkk_consent: kvkkConsent,
        appointment_id: appointmentId || undefined,
      },
      {
        onSuccess: (session) => {
          // Seçili kayıt varsa LivePage'e replayPath olarak geçir; orada
          // mikrofon yerine WS replay mesajı gönderilecek.
          navigate(`/session/${session.id}/live`, {
            state: selectedRecordingPath ? { replayPath: selectedRecordingPath } : undefined,
          })
        },
      }
    )
  }

  if (!hasAppointment) {
    return (
      <div className="mx-auto max-w-2xl">
        <div className="rounded-2xl bg-white dark:bg-slate-800 p-8 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60 text-center">
          <AlertCircle className="mx-auto h-10 w-10 text-amber-500 mb-4" />
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-2">{t('pre_noAppt')}</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">{t('pre_noApptDesc')}</p>
          <button
            onClick={() => navigate('/calendar')}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            {t('pre_goToCalendar')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-2xl bg-white dark:bg-slate-800 p-8 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/30">
            <Mic className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">{t('pre_startSession')}</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">{t('pre_checkInfo')}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Patient Info (read-only, from appointment) */}
          <div className="rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-900/20 p-4 space-y-2">
            <p className="text-xs font-medium text-blue-600 uppercase tracking-wide">
              {t('pre_patientInfo')}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">{t('pre_patient')}</span>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{appointmentPatientName}</p>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">{t('pre_patientId')}</span>
                <p className="text-sm font-mono text-slate-800 dark:text-slate-100">{appointmentPatientId}</p>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">{t('pre_doctor')}</span>
                <p className="text-sm text-slate-800 dark:text-slate-100">{doctorName}</p>
              </div>
            </div>
          </div>

          {showRecordingPicker && (
            <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50/40 dark:bg-amber-900/20 p-4 space-y-3">
              <div className="flex items-start gap-2">
                <History className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
                <div>
                  <h3 className="text-sm font-semibold text-amber-800 dark:text-amber-200">
                    {t('pre_existingRecordings')}
                  </h3>
                  <p className="text-xs text-amber-700 dark:text-amber-300 mt-0.5">
                    {t('pre_existingRecordingsDesc')}
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <button
                  type="button"
                  onClick={() => setSelectedRecordingPath(null)}
                  className={`w-full flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-left transition-colors ${
                    selectedRecordingPath === null
                      ? 'bg-amber-100 dark:bg-amber-900/40 ring-1 ring-amber-300 dark:ring-amber-700 text-amber-900 dark:text-amber-100'
                      : 'bg-white dark:bg-slate-800 hover:bg-amber-50 dark:hover:bg-amber-900/30 text-slate-700 dark:text-slate-200 ring-1 ring-slate-200 dark:ring-slate-700'
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <Mic className="h-4 w-4" />
                    {t('pre_recordNew')}
                  </span>
                  {selectedRecordingPath === null && (
                    <span className="text-xs font-medium">{t('pre_selected')}</span>
                  )}
                </button>

                {recordingItems.map((rec) => {
                  const isSelected = selectedRecordingPath === rec.path
                  const ts = rec.timestamp ? new Date(rec.timestamp * 1000) : null
                  const sizeMb = (rec.size_bytes / (1024 * 1024)).toFixed(1)
                  return (
                    <button
                      key={rec.path}
                      type="button"
                      onClick={() => setSelectedRecordingPath(rec.path)}
                      className={`w-full flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-left transition-colors ${
                        isSelected
                          ? 'bg-amber-100 dark:bg-amber-900/40 ring-1 ring-amber-300 dark:ring-amber-700 text-amber-900 dark:text-amber-100'
                          : 'bg-white dark:bg-slate-800 hover:bg-amber-50 dark:hover:bg-amber-900/30 text-slate-700 dark:text-slate-200 ring-1 ring-slate-200 dark:ring-slate-700'
                      }`}
                    >
                      <div className="flex flex-col items-start gap-0.5">
                        <span className="font-mono text-xs">{rec.filename}</span>
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          {ts ? ts.toLocaleString('tr-TR') : '—'} · {sizeMb} MB
                        </span>
                      </div>
                      {isSelected && (
                        <span className="text-xs font-medium">{t('pre_selected')}</span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-4">
            <div className="flex items-start gap-3">
              <input
                id="kvkkConsent"
                type="checkbox"
                checked={kvkkConsent}
                onChange={(e) => setKvkkConsent(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 dark:border-slate-600 text-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
              />
              <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-200">
                <label htmlFor="kvkkConsent" className="cursor-pointer">
                  {t('pre_kvkkConsent')}
                </label>{' '}
                <button
                  type="button"
                  onClick={() => setKvkkModalOpen(true)}
                  className="font-medium text-blue-600 dark:text-blue-400 underline underline-offset-2 hover:text-blue-700 dark:hover:text-blue-300"
                >
                  {t('pre_kvkkReadLink')}
                </button>
              </p>
            </div>
          </div>

          <KvkkConsentModal
            open={kvkkModalOpen}
            onClose={() => setKvkkModalOpen(false)}
            onAccept={() => setKvkkConsent(true)}
          />

          {createSession.error && (
            <div className="flex items-center gap-3 rounded-lg bg-red-50 dark:bg-red-900/30 p-3 ring-1 ring-red-200 dark:ring-red-800">
              <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
              <p className="text-sm text-red-700 dark:text-red-300">{createSession.error.message}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={!kvkkConsent || createSession.isPending}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {createSession.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('pre_startRecording')}
          </button>
        </form>
      </div>
    </div>
  )
}
