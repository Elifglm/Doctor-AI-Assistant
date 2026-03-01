import { useState, useEffect, useCallback } from 'react'
import {
  User,
  Mic,
  FileText,
  Monitor,
  Shield,
  Trash2,
  AlertCircle,
  Sun,
  Moon,
  BrainCircuit,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../stores/authStore'
import { useUIStore } from '../stores/uiStore'
import { apiClient } from '../services/apiClient'
import type { HealthResponse } from '../types/api'
import { cn } from '../lib/utils'

type TabKey = 'profil' | 'ses' | 'llm' | 'sablonlar' | 'goruntu' | 'gizlilik'

interface TabItem {
  key: TabKey
  label: string
  icon: React.ComponentType<{ className?: string }>
}

const tabs: TabItem[] = [
  { key: 'profil', label: 'Profil', icon: User },
  { key: 'ses', label: 'Ses', icon: Mic },
  { key: 'llm', label: 'LLM', icon: BrainCircuit },
  { key: 'sablonlar', label: 'Şablonlar', icon: FileText },
  { key: 'goruntu', label: 'Görüntü', icon: Monitor },
  { key: 'gizlilik', label: 'Gizlilik', icon: Shield },
]

interface AudioDevice {
  deviceId: string
  label: string
}

function ProfilTab(): React.JSX.Element {
  const user = useAuthStore((s) => s.user)

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Profil Bilgileri</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">
              Görünen Ad
            </label>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-700">
              {user?.display_name ?? 'Bilinmiyor'}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">
              Kullanıcı Adı
            </label>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-700">
              {user?.username ?? 'Bilinmiyor'}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">Rol</label>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-700">
              {user?.role ?? 'Bilinmiyor'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function SesTab(): React.JSX.Element {
  const [devices, setDevices] = useState<AudioDevice[]>([])
  const [selectedDevice, setSelectedDevice] = useState('')
  const [permissionError, setPermissionError] = useState(false)

  const loadDevices = useCallback(async () => {
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true })
      const allDevices = await navigator.mediaDevices.enumerateDevices()
      const audioInputs = allDevices
        .filter((d) => d.kind === 'audioinput')
        .map((d) => ({
          deviceId: d.deviceId,
          label: d.label || `Mikrofon ${d.deviceId.slice(0, 8)}`,
        }))
      setDevices(audioInputs)
      if (audioInputs.length > 0 && !selectedDevice) {
        setSelectedDevice(audioInputs[0].deviceId)
      }
    } catch {
      setPermissionError(true)
    }
  }, [selectedDevice])

  useEffect(() => {
    void loadDevices()
  }, [loadDevices])

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Ses Ayarları</h3>
        <div className="space-y-4">
          <div>
            <label
              htmlFor="micSelect"
              className="block text-sm font-medium text-slate-600 mb-1"
            >
              Mikrofon Seçimi
            </label>
            {permissionError ? (
              <div className="flex items-center gap-2 rounded-lg bg-amber-50 p-3 ring-1 ring-amber-200">
                <AlertCircle className="h-4 w-4 text-amber-600 shrink-0" />
                <p className="text-sm text-amber-700">
                  Mikrofon erişimi reddedildi. Lütfen tarayıcı ayarlarından izin verin.
                </p>
              </div>
            ) : (
              <select
                id="micSelect"
                value={selectedDevice}
                onChange={(e) => setSelectedDevice(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                {devices.map((device) => (
                  <option key={device.deviceId} value={device.deviceId}>
                    {device.label}
                  </option>
                ))}
                {devices.length === 0 && (
                  <option value="">Mikrofon bulunamadı</option>
                )}
              </select>
            )}
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm text-slate-600">
              Ses kalitesi: Mono kanal, 16kHz örnekleme oranı. Tıbbi konuşmalar için optimize
              edilmiştir.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function LLMTab(): React.JSX.Element {
  const { data: health, isLoading, refetch } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: () => apiClient.get<HealthResponse>('/api/v1/health'),
    refetchInterval: 10000,
  })

  const [isTesting, setIsTesting] = useState(false)

  const handleTestConnection = useCallback(async () => {
    setIsTesting(true)
    try {
      await refetch()
    } finally {
      setIsTesting(false)
    }
  }, [refetch])

  const ollamaConnected = health?.ollama_status === 'connected'
  const modelLoaded = health?.ollama_model_loaded ?? false
  const ragDocs = health?.rag_doc_count ?? 0

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">LLM Ayarları</h3>

        {/* Connection status */}
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
            <h4 className="text-sm font-semibold text-slate-700">Ollama Durumu</h4>

            <div className="space-y-2">
              {/* Ollama connection */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600">Ollama Bağlantısı</span>
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
                ) : ollamaConnected ? (
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                    <span className="text-sm text-emerald-700">Bağlı</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <XCircle className="h-4 w-4 text-red-500" />
                    <span className="text-sm text-red-700">Bağlı Değil</span>
                  </div>
                )}
              </div>

              {/* Model loaded */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600">Model Yüklü</span>
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
                ) : modelLoaded ? (
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                    <span className="text-sm text-emerald-700">Evet</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <XCircle className="h-4 w-4 text-amber-500" />
                    <span className="text-sm text-amber-700">Hayır</span>
                  </div>
                )}
              </div>

              {/* RAG documents */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600">RAG Belge Sayısı</span>
                <span className="text-sm text-slate-700 font-medium">{ragDocs}</span>
              </div>

              {/* GPU */}
              {health?.gpu_available && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">GPU</span>
                  <span className="text-sm text-slate-700">{health.gpu_name}</span>
                </div>
              )}
              {health?.gpu_memory_used_mb != null && health?.gpu_memory_total_mb != null && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">GPU Bellek</span>
                  <span className="text-sm text-slate-700">
                    {health.gpu_memory_used_mb} / {health.gpu_memory_total_mb} MB
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Test button */}
          <button
            type="button"
            onClick={() => void handleTestConnection()}
            disabled={isTesting}
            className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
          >
            {isTesting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <BrainCircuit className="h-4 w-4" />
            )}
            Bağlantı Testi
          </button>

          {/* Help text */}
          {!ollamaConnected && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <h4 className="text-sm font-semibold text-amber-800 mb-1">
                Ollama Bağlantısı Kurulamadı
              </h4>
              <p className="text-sm text-amber-700">
                Ollama&apos;nın çalıştığından emin olun. Terminal&apos;de{' '}
                <code className="rounded bg-amber-100 px-1 py-0.5 text-xs font-mono">
                  ollama serve
                </code>{' '}
                komutuyla başlatabilirsiniz.
              </p>
            </div>
          )}

          {ollamaConnected && !modelLoaded && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <h4 className="text-sm font-semibold text-amber-800 mb-1">
                Model Yüklenmemiş
              </h4>
              <p className="text-sm text-amber-700">
                Terminal&apos;de{' '}
                <code className="rounded bg-amber-100 px-1 py-0.5 text-xs font-mono">
                  ollama pull qwen3:14b
                </code>{' '}
                komutuyla modeli indirin.
              </p>
            </div>
          )}

          {/* Model info */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2">
            <h4 className="text-sm font-semibold text-slate-700">Model Bilgisi</h4>
            <p className="text-sm text-slate-600">
              <strong>Birincil:</strong> Qwen3 14B (~12GB VRAM, Türkçe destekli)
            </p>
            <p className="text-sm text-slate-600">
              <strong>Yedek:</strong> Qwen3 8B (~6GB VRAM, daha hızlı)
            </p>
            <p className="text-sm text-slate-500 text-xs mt-2">
              Tüm işlem yerel olarak yapılır. Veriler dışarıya gönderilmez (KVKK uyumlu).
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function SablonlarTab(): React.JSX.Element {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Rapor Şablonları</h3>
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 p-12">
          <FileText className="h-10 w-10 text-slate-300 mb-3" />
          <p className="text-sm text-slate-500 text-center">
            Rapor şablonları yakın zamanda eklenecek
          </p>
          <p className="text-xs text-slate-400 mt-1 text-center">
            Özel anamnez şablonları tanımlayabileceksiniz
          </p>
        </div>
      </div>
    </div>
  )
}

function GoruntuTab(): React.JSX.Element {
  const theme = useUIStore((s) => s.theme)
  const setTheme = useUIStore((s) => s.setTheme)
  const fontSize = useUIStore((s) => s.fontSize)
  const setFontSize = useUIStore((s) => s.setFontSize)

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Görüntü Ayarları</h3>
        <div className="space-y-6">
          {/* Theme toggle */}
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-2">Tema</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setTheme('light')}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                  theme === 'light'
                    ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                )}
              >
                <Sun className="h-4 w-4" />
                Açık
              </button>
              <button
                type="button"
                onClick={() => setTheme('dark')}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                  theme === 'dark'
                    ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                )}
              >
                <Moon className="h-4 w-4" />
                Koyu
              </button>
            </div>
          </div>

          {/* Font size slider */}
          <div>
            <label htmlFor="fontSizeSlider" className="block text-sm font-medium text-slate-600 mb-2">
              Yazı Boyutu: {fontSize}px
            </label>
            <input
              id="fontSizeSlider"
              type="range"
              min={14}
              max={24}
              step={1}
              value={fontSize}
              onChange={(e) => setFontSize(parseInt(e.target.value, 10))}
              className="w-full accent-blue-600"
            />
            <div className="flex justify-between text-xs text-slate-400 mt-1">
              <span>14px</span>
              <span>24px</span>
            </div>
          </div>

          {/* Preview */}
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-2">
              Önizleme
            </label>
            <div
              className="rounded-lg border border-slate-200 bg-white p-4"
              style={{ fontSize: `${fontSize}px` }}
            >
              <p className="text-slate-700">
                Bu bir önizleme metnidir. Yazı boyutu değiştikçe bu metin de değişecektir.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

interface PurgeResponse {
  message: string
  deleted_sessions: number
  deleted_segments: number
  deleted_reports: number
  deleted_audit_logs: number
  total_deleted: number
}

function GizlilikTab(): React.JSX.Element {
  const [showConfirmation, setShowConfirmation] = useState(false)
  const [purging, setPurging] = useState(false)
  const [purgeResult, setPurgeResult] = useState<string | null>(null)
  const [purgeError, setPurgeError] = useState<string | null>(null)

  const handlePurge = useCallback(async () => {
    setPurging(true)
    setPurgeError(null)
    setPurgeResult(null)
    try {
      const result = await apiClient.delete<PurgeResponse>('/api/v1/data/purge')
      setPurgeResult(
        `${result.total_deleted} kayıt silindi (${result.deleted_sessions} görüşme, ` +
        `${result.deleted_segments} segment, ${result.deleted_reports} rapor, ` +
        `${result.deleted_audit_logs} denetim kaydı).`
      )
    } catch (err: unknown) {
      if (err instanceof Error) {
        setPurgeError(err.message)
      } else {
        setPurgeError('Veriler silinirken bir hata oluştu')
      }
    } finally {
      setPurging(false)
      setShowConfirmation(false)
    }
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Gizlilik ve Güvenlik</h3>
        <div className="space-y-4">
          {/* KVKK info */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2">
            <h4 className="text-sm font-semibold text-slate-700">KVKK Uyumluluğu</h4>
            <p className="text-sm text-slate-600 leading-relaxed">
              Bu uygulama, 6698 sayılı Kişisel Verilerin Korunması Kanunu (KVKK) kapsamında
              geliştirilmiştir. Hasta ses kayıtları ve kişisel sağlık verileri, ilgili
              mevzuat doğrultusunda işlenmekte ve saklanmaktadır.
            </p>
            <p className="text-sm text-slate-600 leading-relaxed">
              Verileriniz şifrelenmiş bağlantı üzerinden iletilmekte ve güvenli sunucularda
              depolanmaktadır. Her kayıt işlemi öncesinde hasta onamının alınması
              zorunludur.
            </p>
            <p className="text-sm text-slate-600 leading-relaxed">
              LLM (yapay zeka) işlemleri tamamen yerel olarak gerçekleştirilmektedir.
              Hasta verileri hiçbir dış sunucuya gönderilmez.
            </p>
          </div>

          {/* Delete all data */}
          <div className="rounded-lg border border-red-200 bg-red-50 p-4">
            <h4 className="text-sm font-semibold text-red-800 mb-2">Tehlikeli Bölge</h4>
            {!showConfirmation ? (
              <button
                type="button"
                onClick={() => setShowConfirmation(true)}
                disabled={purging}
                className="flex items-center gap-2 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 transition-colors disabled:opacity-50"
              >
                {purging ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                Tüm verileri sil
              </button>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-red-700">
                  Bu işlem geri alınamaz. Tüm görüşme verileriniz, raporlarınız ve kayıtlarınız
                  kalıcı olarak silinecektir. Devam etmek istediğinizden emin misiniz?
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowConfirmation(false)}
                    disabled={purging}
                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
                  >
                    İptal
                  </button>
                  <button
                    type="button"
                    onClick={() => void handlePurge()}
                    disabled={purging}
                    className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors disabled:opacity-50"
                  >
                    {purging && <Loader2 className="h-4 w-4 animate-spin" />}
                    Evet, tüm verileri sil
                  </button>
                </div>
              </div>
            )}

            {/* Success message */}
            {purgeResult && (
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-emerald-50 p-3 ring-1 ring-emerald-200">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                <p className="text-sm text-emerald-700">{purgeResult}</p>
              </div>
            )}

            {/* Error message */}
            {purgeError && (
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 p-3 ring-1 ring-red-200">
                <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
                <p className="text-sm text-red-700">{purgeError}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

const tabComponents: Record<TabKey, React.ComponentType> = {
  profil: ProfilTab,
  ses: SesTab,
  llm: LLMTab,
  sablonlar: SablonlarTab,
  goruntu: GoruntuTab,
  gizlilik: GizlilikTab,
}

export function SettingsPage(): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>('profil')

  const ActiveTabComponent = tabComponents[activeTab]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Ayarlar</h1>
        <p className="text-sm text-slate-500 mt-1">Uygulama tercihlerinizi yönetin</p>
      </div>

      <div className="flex gap-6">
        {/* Tab navigation */}
        <div className="w-48 shrink-0">
          <nav className="space-y-1">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors text-left',
                  activeTab === tab.key
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'
                )}
              >
                <tab.icon className="h-4 w-4 shrink-0" />
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab content */}
        <div className="flex-1 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200/60">
          <div
            key={activeTab}
            className="animate-fade-in"
            style={{
              animation: 'fadeIn 150ms ease-in-out',
            }}
          >
            <ActiveTabComponent />
          </div>
          <style>{`
            @keyframes fadeIn {
              from { opacity: 0; }
              to { opacity: 1; }
            }
          `}</style>
        </div>
      </div>
    </div>
  )
}
