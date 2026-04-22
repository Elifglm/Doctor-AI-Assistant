import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Mic, Loader2, AlertCircle } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useCreateSession } from '../hooks/useSession'
import { useT } from '../hooks/useT'
import type { VisitType } from '../types/session'

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

  // If no appointment data, redirect to calendar
  const hasAppointment = Boolean(appointmentPatientId && appointmentPatientName)

  const visitTypeOptions: { value: VisitType; labelKey: string }[] = [
    { value: 'ilk_muayene', labelKey: 'pre_ilkMuayene' },
    { value: 'kontrol', labelKey: 'pre_kontrol' },
    { value: 'konsultasyon', labelKey: 'pre_konsultasyon' },
    { value: 'acil', labelKey: 'pre_acil' },
  ]

  const [visitType, setVisitType] = useState<VisitType>('ilk_muayene')
  const [preDiagnosis, setPreDiagnosis] = useState('')
  const [location, setLocation] = useState('')
  const [kvkkConsent, setKvkkConsent] = useState(false)

  const doctorName = appointmentProvider || user?.display_name || ''

  const handleSubmit = (e: FormEvent<HTMLFormElement>): void => {
    e.preventDefault()

    if (!kvkkConsent) return

    createSession.mutate(
      {
        patient_id: appointmentPatientId,
        patient_name: appointmentPatientName,
        visit_type: visitType,
        doctor_name: doctorName,
        pre_diagnosis: preDiagnosis || undefined,
        location: location || undefined,
        kvkk_consent: kvkkConsent,
      },
      {
        onSuccess: (session) => {
          navigate(`/session/${session.id}/live`)
        },
      }
    )
  }

  if (!hasAppointment) {
    return (
      <div className="mx-auto max-w-2xl">
        <div className="rounded-2xl bg-white p-8 shadow-sm ring-1 ring-slate-200/60 text-center">
          <AlertCircle className="mx-auto h-10 w-10 text-amber-500 mb-4" />
          <h2 className="text-lg font-semibold text-slate-800 mb-2">{t('pre_noAppt')}</h2>
          <p className="text-sm text-slate-500 mb-6">{t('pre_noApptDesc')}</p>
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
      <div className="rounded-2xl bg-white p-8 shadow-sm ring-1 ring-slate-200/60">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50">
            <Mic className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-800">{t('pre_startSession')}</h1>
            <p className="text-sm text-slate-500">{t('pre_checkInfo')}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Patient Info (read-only, from appointment) */}
          <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 space-y-2">
            <p className="text-xs font-medium text-blue-600 uppercase tracking-wide">
              {t('pre_patientInfo')}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-xs text-slate-500">{t('pre_patient')}</span>
                <p className="text-sm font-semibold text-slate-800">{appointmentPatientName}</p>
              </div>
              <div>
                <span className="text-xs text-slate-500">{t('pre_patientId')}</span>
                <p className="text-sm font-mono text-slate-800">{appointmentPatientId}</p>
              </div>
              <div>
                <span className="text-xs text-slate-500">{t('pre_doctor')}</span>
                <p className="text-sm text-slate-800">{doctorName}</p>
              </div>
            </div>
          </div>

          <div>
            <label htmlFor="visitType" className="mb-1.5 block text-sm font-medium text-slate-700">
              {t('pre_visitType')}
            </label>
            <select
              id="visitType"
              value={visitType}
              onChange={(e) => setVisitType(e.target.value as VisitType)}
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              {visitTypeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {t(opt.labelKey)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="preDiagnosis"
              className="mb-1.5 block text-sm font-medium text-slate-700"
            >
              {t('pre_preDiagnosis')}
            </label>
            <textarea
              id="preDiagnosis"
              value={preDiagnosis}
              onChange={(e) => setPreDiagnosis(e.target.value)}
              placeholder={t('pre_preDiagnosisPlaceholder')}
              rows={3}
              className="w-full resize-none rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          <div>
            <label htmlFor="location" className="mb-1.5 block text-sm font-medium text-slate-700">
              {t('pre_location')}
            </label>
            <input
              id="location"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder={t('pre_locationPlaceholder')}
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={kvkkConsent}
                onChange={(e) => setKvkkConsent(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-sm text-slate-700 leading-relaxed">
                {t('pre_kvkkConsent')}
              </span>
            </label>
          </div>

          {createSession.error && (
            <div className="flex items-center gap-3 rounded-lg bg-red-50 p-3 ring-1 ring-red-200">
              <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
              <p className="text-sm text-red-700">{createSession.error.message}</p>
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
