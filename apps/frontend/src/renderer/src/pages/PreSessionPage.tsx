import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mic, Loader2, AlertCircle } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useCreateSession } from '../hooks/useSession'
import type { VisitType } from '../types/session'

const visitTypeOptions: { value: VisitType; label: string }[] = [
  { value: 'ilk_muayene', label: 'İlk Muayene' },
  { value: 'kontrol', label: 'Kontrol' },
  { value: 'konsultasyon', label: 'Konsültasyon' },
  { value: 'acil', label: 'Acil' },
]

export function PreSessionPage(): React.JSX.Element {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const createSession = useCreateSession()

  const [patientId, setPatientId] = useState('')
  const [visitType, setVisitType] = useState<VisitType>('ilk_muayene')
  const [doctorName, setDoctorName] = useState(user?.display_name ?? '')
  const [preDiagnosis, setPreDiagnosis] = useState('')
  const [location, setLocation] = useState('')
  const [kvkkConsent, setKvkkConsent] = useState(false)

  const handleSubmit = (e: FormEvent<HTMLFormElement>): void => {
    e.preventDefault()

    if (!kvkkConsent) return

    createSession.mutate(
      {
        patient_id: patientId || undefined,
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

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-2xl bg-white p-8 shadow-sm ring-1 ring-slate-200/60">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50">
            <Mic className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-800">Yeni Görüşme Ayarları</h1>
            <p className="text-sm text-slate-500">Kayda başlamadan önce bilgileri doldurun</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="patientId" className="mb-1.5 block text-sm font-medium text-slate-700">
              Hasta ID
            </label>
            <input
              id="patientId"
              type="text"
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              placeholder="Hasta numarası"
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          <div>
            <label htmlFor="visitType" className="mb-1.5 block text-sm font-medium text-slate-700">
              Ziyaret Tipi
            </label>
            <select
              id="visitType"
              value={visitType}
              onChange={(e) => setVisitType(e.target.value as VisitType)}
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              {visitTypeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="doctorName"
              className="mb-1.5 block text-sm font-medium text-slate-700"
            >
              Doktor Adı
            </label>
            <input
              id="doctorName"
              type="text"
              value={doctorName}
              onChange={(e) => setDoctorName(e.target.value)}
              required
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          <div>
            <label
              htmlFor="preDiagnosis"
              className="mb-1.5 block text-sm font-medium text-slate-700"
            >
              Ön Tanı
            </label>
            <textarea
              id="preDiagnosis"
              value={preDiagnosis}
              onChange={(e) => setPreDiagnosis(e.target.value)}
              placeholder="Ön tanı notu..."
              rows={3}
              className="w-full resize-none rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          <div>
            <label htmlFor="location" className="mb-1.5 block text-sm font-medium text-slate-700">
              Konum
            </label>
            <input
              id="location"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Poliklinik / Oda"
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
                Hasta KVKK aydınlatma metnini okumuş ve ses kaydına onay vermiştir
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
            Kaydı Başlat
          </button>
        </form>
      </div>
    </div>
  )
}
