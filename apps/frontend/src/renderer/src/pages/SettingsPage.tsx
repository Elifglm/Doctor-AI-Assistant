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
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useUIStore } from '../stores/uiStore'
import { cn } from '../lib/utils'

type TabKey = 'profil' | 'ses' | 'sablonlar' | 'goruntu' | 'gizlilik'

interface TabItem {
  key: TabKey
  label: string
  icon: React.ComponentType<{ className?: string }>
}

const tabs: TabItem[] = [
  { key: 'profil', label: 'Profil', icon: User },
  { key: 'ses', label: 'Ses', icon: Mic },
  { key: 'sablonlar', label: 'Sablonlar', icon: FileText },
  { key: 'goruntu', label: 'Goruntu', icon: Monitor },
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
              Gorunen Ad
            </label>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-700">
              {user?.display_name ?? 'Bilinmiyor'}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">
              Kullanici Adi
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
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Ses Ayarlari</h3>
        <div className="space-y-4">
          <div>
            <label
              htmlFor="micSelect"
              className="block text-sm font-medium text-slate-600 mb-1"
            >
              Mikrofon Secimi
            </label>
            {permissionError ? (
              <div className="flex items-center gap-2 rounded-lg bg-amber-50 p-3 ring-1 ring-amber-200">
                <AlertCircle className="h-4 w-4 text-amber-600 shrink-0" />
                <p className="text-sm text-amber-700">
                  Mikrofon erisimi reddedildi. Lutfen tarayici ayarlarindan izin verin.
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
                  <option value="">Mikrofon bulunamadi</option>
                )}
              </select>
            )}
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm text-slate-600">
              Ses kalitesi: Mono kanal, 16kHz ornekleme orani. Tibbi konusmalar icin optimize
              edilmistir.
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
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Rapor Sablonlari</h3>
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 p-12">
          <FileText className="h-10 w-10 text-slate-300 mb-3" />
          <p className="text-sm text-slate-500 text-center">
            Rapor sablonlari yakin zamanda eklenecek
          </p>
          <p className="text-xs text-slate-400 mt-1 text-center">
            Ozel anamnez sablonlari tanimlayabileceksiniz
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
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Goruntu Ayarlari</h3>
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
                Acik
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
              Yazi Boyutu: {fontSize}px
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
              Onizleme
            </label>
            <div
              className="rounded-lg border border-slate-200 bg-white p-4"
              style={{ fontSize: `${fontSize}px` }}
            >
              <p className="text-slate-700">
                Bu bir onizleme metnidir. Yazi boyutu degistikce bu metin de degisecektir.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function GizlilikTab(): React.JSX.Element {
  const [showConfirmation, setShowConfirmation] = useState(false)

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Gizlilik ve Guvenlik</h3>
        <div className="space-y-4">
          {/* KVKK info */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2">
            <h4 className="text-sm font-semibold text-slate-700">KVKK Uyumlulugu</h4>
            <p className="text-sm text-slate-600 leading-relaxed">
              Bu uygulama, 6698 sayili Kisisel Verilerin Korunmasi Kanunu (KVKK) kapsaminda
              gelistirilmistir. Hasta ses kayitlari ve kisisel saglik verileri, ilgili
              mevzuat dogrultusunda islenmekte ve saklanmaktadir.
            </p>
            <p className="text-sm text-slate-600 leading-relaxed">
              Verileriniz sifrelenmis baglanti uzerinden iletilmekte ve guvenli sunucularda
              depolanmaktadir. Her kayit islemi oncesinde hasta onaminin alinmasi
              zorunludur.
            </p>
          </div>

          {/* Delete all data */}
          <div className="rounded-lg border border-red-200 bg-red-50 p-4">
            <h4 className="text-sm font-semibold text-red-800 mb-2">Tehlikeli Bolge</h4>
            {!showConfirmation ? (
              <button
                type="button"
                onClick={() => setShowConfirmation(true)}
                className="flex items-center gap-2 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 transition-colors"
              >
                <Trash2 className="h-4 w-4" />
                Tum verileri sil
              </button>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-red-700">
                  Bu islem geri alinamaz. Tum oturum verileriniz, raporlariniz ve kayitlariniz
                  kalici olarak silinecektir. Devam etmek istediginizden emin misiniz?
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowConfirmation(false)}
                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                  >
                    Iptal
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      // Placeholder - actual deletion not implemented
                      setShowConfirmation(false)
                    }}
                    className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors"
                  >
                    Evet, tum verileri sil
                  </button>
                </div>
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
        <p className="text-sm text-slate-500 mt-1">Uygulama tercihlerinizi yonetin</p>
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
          <ActiveTabComponent />
        </div>
      </div>
    </div>
  )
}
