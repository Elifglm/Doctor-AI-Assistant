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
  Save,
  AlertTriangle,
} from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../stores/authStore'
import { useUIStore } from '../stores/uiStore'
import { apiClient } from '../services/apiClient'
import { useT } from '../hooks/useT'
import type { HealthResponse, LLMSettingsResponse, LLMSettingsUpdate } from '../types/api'
import { cn } from '../lib/utils'

type TabKey = 'profil' | 'ses' | 'llm' | 'sablonlar' | 'goruntu' | 'gizlilik'

function ProfilTab(): React.JSX.Element {
  const user = useAuthStore((s) => s.user)
  const t = useT()

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('settings_profile_title')}</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">
              {t('settings_displayName')}
            </label>
            <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-3.5 py-2.5 text-sm text-slate-700 dark:text-slate-200">
              {user?.display_name ?? t('settings_unknown')}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">
              {t('settings_username')}
            </label>
            <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-3.5 py-2.5 text-sm text-slate-700 dark:text-slate-200">
              {user?.username ?? t('settings_unknown')}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">{t('settings_role')}</label>
            <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-3.5 py-2.5 text-sm text-slate-700 dark:text-slate-200">
              {user?.role === 'admin' ? t('settings_admin') : t('settings_doctor')}
            </div>
          </div>
          {user?.brans && (
            <div>
              <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">{t('settings_specialty')}</label>
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-3.5 py-2.5 text-sm text-slate-700 dark:text-slate-200">
                {user.brans === 'dahiliye' ? t('settings_internalMed') : t('settings_ortho')}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SesTab(): React.JSX.Element {
  const [devices, setDevices] = useState<{ deviceId: string; label: string }[]>([])
  const micDeviceId = useUIStore((s) => s.micDeviceId)
  const setMicDeviceId = useUIStore((s) => s.setMicDeviceId)
  const [permissionError, setPermissionError] = useState(false)
  const t = useT()

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
      // If saved device is no longer available, fall back to first
      if (audioInputs.length > 0) {
        const stillAvailable = micDeviceId && audioInputs.some((d) => d.deviceId === micDeviceId)
        if (!stillAvailable) {
          setMicDeviceId(audioInputs[0].deviceId)
        }
      }
      setPermissionError(false)
    } catch {
      setPermissionError(true)
    }
  }, [micDeviceId, setMicDeviceId])

  useEffect(() => {
    void loadDevices()
  }, [loadDevices])

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('settings_audio_title')}</h3>
        <div className="space-y-4">
          <div>
            <label
              htmlFor="micSelect"
              className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1"
            >
              {t('settings_micSelection')}
            </label>
            {permissionError ? (
              <div className="flex items-start gap-2 rounded-lg bg-amber-50 dark:bg-amber-900/30 p-3 ring-1 ring-amber-200 dark:ring-amber-800">
                <AlertCircle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                <div className="flex-1 space-y-2">
                  <p className="text-sm text-amber-700 dark:text-amber-300">{t('settings_micDenied')}</p>
                  <button
                    type="button"
                    onClick={() => void loadDevices()}
                    className="inline-flex items-center gap-1.5 rounded-md bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-700 transition-colors"
                  >
                    {t('settings_micRetry')}
                  </button>
                </div>
              </div>
            ) : (
              <select
                id="micSelect"
                value={micDeviceId ?? ''}
                onChange={(e) => setMicDeviceId(e.target.value || null)}
                className="w-full rounded-lg border border-slate-300 dark:border-slate-600 px-3.5 py-2.5 text-sm text-slate-800 dark:text-slate-100 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                {devices.map((device) => (
                  <option key={device.deviceId} value={device.deviceId}>
                    {device.label}
                  </option>
                ))}
                {devices.length === 0 && (
                  <option value="">{t('settings_micNotFound')}</option>
                )}
              </select>
            )}
          </div>
          <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-4">
            <p className="text-sm text-slate-600 dark:text-slate-300">{t('settings_audioQuality')}</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function LLMTab(): React.JSX.Element {
  const queryClient = useQueryClient()
  const t = useT()

  const { data: health, isLoading: healthLoading, refetch: refetchHealth } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: () => apiClient.get<HealthResponse>('/api/v1/health'),
    refetchInterval: 10000,
  })

  const { data: llmSettings, isLoading: settingsLoading } = useQuery<LLMSettingsResponse>({
    queryKey: ['llm-settings'],
    queryFn: () => apiClient.get<LLMSettingsResponse>('/api/v1/settings/llm'),
  })

  const [mode, setMode] = useState<'local' | 'api'>('local')
  const [geminiApiKey, setGeminiApiKey] = useState('')
  const [geminiModel, setGeminiModel] = useState('gemini-2.0-flash')
  const [fallbackEnabled, setFallbackEnabled] = useState(true)
  const [temperature, setTemperature] = useState(0.3)
  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    if (llmSettings) {
      setMode(llmSettings.mode)
      setGeminiModel(llmSettings.gemini_model)
      setFallbackEnabled(llmSettings.ollama_fallback_enabled)
      setTemperature(llmSettings.temperature)
    }
  }, [llmSettings])

  const saveMutation = useMutation({
    mutationFn: (payload: LLMSettingsUpdate) =>
      apiClient.put<LLMSettingsResponse>('/api/v1/settings/llm', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['llm-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['health'] })
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
    },
  })

  const handleSave = (): void => {
    const payload: LLMSettingsUpdate = {
      mode,
      gemini_model: geminiModel,
      ollama_fallback_enabled: fallbackEnabled,
      temperature,
    }
    if (geminiApiKey) {
      payload.gemini_api_key = geminiApiKey
    }
    saveMutation.mutate(payload)
  }

  const handleTestConnection = useCallback(async () => {
    setIsTesting(true)
    setTestResult(null)
    try {
      const result = await refetchHealth()
      const connected = result.data?.ollama_status === 'connected'
      setTestResult(connected ? 'success' : 'error')
    } catch {
      setTestResult('error')
    } finally {
      setIsTesting(false)
      setTimeout(() => setTestResult(null), 5000)
    }
  }, [refetchHealth])

  const ollamaConnected = health?.ollama_status === 'connected'
  const modelLoaded = health?.ollama_model_loaded ?? false
  const ragDocs = health?.rag_doc_count ?? 0
  const isLoading = healthLoading || settingsLoading

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('settings_llm_title')}</h3>

        <div className="space-y-4">
          {/* Mode selection */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-4 space-y-3">
            <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('settings_llmMode')}</h4>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setMode('local')}
                className={cn(
                  'flex-1 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors text-center',
                  mode === 'local'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 ring-1 ring-blue-200 dark:ring-blue-800'
                    : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/50 '
                )}
              >
                {t('settings_local')}
              </button>
              <button
                type="button"
                onClick={() => setMode('api')}
                className={cn(
                  'flex-1 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors text-center',
                  mode === 'api'
                    ? 'bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 ring-1 ring-violet-200 dark:ring-violet-800'
                    : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/50 '
                )}
              >
                {t('settings_api')}
              </button>
            </div>
          </div>

          {/* KVKK warning for API mode */}
          {mode === 'api' && (
            <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/30 p-4">
              <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-amber-800 dark:text-amber-200">{t('settings_kvkkWarning')}</h4>
                <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">{t('settings_kvkkWarningMsg')}</p>
              </div>
            </div>
          )}

          {/* Local (Ollama) settings */}
          {mode === 'local' && (
            <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-4 space-y-3">
              <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('settings_ollamaStatus')}</h4>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600 dark:text-slate-300">{t('settings_connection')}</span>
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-slate-400 dark:text-slate-500" />
                  ) : ollamaConnected ? (
                    <div className="flex items-center gap-1.5">
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      <span className="text-sm text-emerald-700 dark:text-emerald-300">{t('settings_connected')}</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <XCircle className="h-4 w-4 text-red-500" />
                      <span className="text-sm text-red-700 dark:text-red-300">{t('settings_notConnected')}</span>
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600 dark:text-slate-300">{t('settings_model')}</span>
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-slate-400 dark:text-slate-500" />
                  ) : modelLoaded ? (
                    <div className="flex items-center gap-1.5">
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      <span className="text-sm text-emerald-700 dark:text-emerald-300">
                        {health?.llm_model_name || t('settings_loaded')}
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <XCircle className="h-4 w-4 text-amber-500" />
                      <span className="text-sm text-amber-700 dark:text-amber-300">{t('settings_notLoaded')}</span>
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600 dark:text-slate-300">{t('settings_ragDocs')}</span>
                  <span className="text-sm text-slate-700 dark:text-slate-200 font-medium">{ragDocs}</span>
                </div>

                {health?.gpu_available && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-600 dark:text-slate-300">{t('settings_gpu')}</span>
                    <span className="text-sm text-slate-700 dark:text-slate-200">{health.gpu_name}</span>
                  </div>
                )}
              </div>

              {/* Fallback toggle */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-200 dark:border-slate-700">
                <div>
                  <span className="text-sm text-slate-600 dark:text-slate-300">{t('settings_fallbackModel')}</span>
                  <p className="text-xs text-slate-400 dark:text-slate-500">{t('settings_fallbackDesc')}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setFallbackEnabled(!fallbackEnabled)}
                  className={cn(
                    'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors',
                    fallbackEnabled ? 'bg-blue-600' : 'bg-slate-200 dark:bg-slate-700'
                  )}
                >
                  <span
                    className={cn(
                      'pointer-events-none inline-block h-5 w-5 rounded-full bg-white dark:bg-slate-800 shadow transition-transform',
                      fallbackEnabled ? 'translate-x-5' : 'translate-x-0'
                    )}
                  />
                </button>
              </div>

              {/* Help text */}
              {!ollamaConnected && (
                <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/30 p-3 mt-2">
                  <p className="text-sm text-amber-700 dark:text-amber-300">
                    {t('settings_ollamaStartCmd').split(':')[0]}:{' '}
                    <code className="rounded bg-amber-100 dark:bg-amber-900/40 px-1 py-0.5 text-xs font-mono">
                      {t('settings_ollamaStartCmd').split(': ')[1] ?? 'ollama serve'}
                    </code>
                  </p>
                </div>
              )}
            </div>
          )}

          {/* API (Gemini) settings */}
          {mode === 'api' && (
            <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-4 space-y-3">
              <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('settings_geminiSettings')}</h4>

              <div>
                <label htmlFor="geminiApiKey" className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">
                  {t('settings_apiKey')}
                </label>
                <input
                  id="geminiApiKey"
                  type="password"
                  value={geminiApiKey}
                  onChange={(e) => setGeminiApiKey(e.target.value)}
                  placeholder={llmSettings?.gemini_api_key_set ? '••••••••••••••••' : t('settings_apiKeyPlaceholder')}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-600 px-3.5 py-2.5 text-sm text-slate-800 dark:text-slate-100 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
                />
                {llmSettings?.gemini_api_key_set && !geminiApiKey && (
                  <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{t('settings_apiKeySet')}</p>
                )}
              </div>

              <div>
                <label htmlFor="geminiModel" className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">
                  {t('settings_model')}
                </label>
                <select
                  id="geminiModel"
                  value={geminiModel}
                  onChange={(e) => setGeminiModel(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-600 px-3.5 py-2.5 text-sm text-slate-800 dark:text-slate-100 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
                >
                  <option value="gemini-2.5-flash">Gemini 2.5 Flash ({t('gemini_fast')})</option>
                  <option value="gemini-2.5-pro">Gemini 2.5 Pro ({t('gemini_quality')})</option>
                  <option value="gemini-2.0-flash">Gemini 2.0 Flash ({t('gemini_legacy')})</option>
                </select>
              </div>

              {/* Connection status */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-200 dark:border-slate-700">
                <span className="text-sm text-slate-600 dark:text-slate-300">{t('settings_connectionStatus')}</span>
                {health?.llm_provider === 'gemini' && health?.ollama_status === 'connected' ? (
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                    <span className="text-sm text-emerald-700 dark:text-emerald-300">{t('settings_connected')}</span>
                  </div>
                ) : health?.llm_provider === 'gemini' ? (
                  <div className="flex items-center gap-1.5">
                    <XCircle className="h-4 w-4 text-red-500" />
                    <span className="text-sm text-red-700 dark:text-red-300">{t('settings_notConnected')}</span>
                  </div>
                ) : (
                  <span className="text-sm text-slate-400 dark:text-slate-500">{t('settings_notSaved')}</span>
                )}
              </div>
            </div>
          )}

          {/* Common parameters */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-4 space-y-3">
            <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('settings_params')}</h4>
            <div>
              <label htmlFor="temperatureSlider" className="block text-sm text-slate-600 dark:text-slate-300 mb-1">
                {t('settings_temperature', { value: temperature.toFixed(1) })}
              </label>
              <input
                id="temperatureSlider"
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-blue-600"
              />
              <div className="flex justify-between text-xs text-slate-400 dark:text-slate-500 mt-1">
                <span>{t('settings_tempDeterministic')}</span>
                <span>{t('settings_tempCreative')}</span>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleSave}
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {saveMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              {t('settings_save')}
            </button>

            <button
              type="button"
              onClick={() => void handleTestConnection()}
              disabled={isTesting}
              className="flex items-center gap-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/50  transition-colors disabled:opacity-50"
            >
              {isTesting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <BrainCircuit className="h-4 w-4" />
              )}
              {t('settings_testConnection')}
            </button>

            {saveSuccess && (
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span className="text-sm text-emerald-700 dark:text-emerald-300">{t('settings_saved')}</span>
              </div>
            )}

            {saveMutation.isError && (
              <div className="flex items-center gap-1.5">
                <AlertCircle className="h-4 w-4 text-red-500" />
                <span className="text-sm text-red-700 dark:text-red-300">{t('settings_saveError')}</span>
              </div>
            )}

            {testResult === 'success' && (
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span className="text-sm text-emerald-700 dark:text-emerald-300">{t('settings_connectionSuccess')}</span>
              </div>
            )}

            {testResult === 'error' && (
              <div className="flex items-center gap-1.5">
                <AlertCircle className="h-4 w-4 text-red-500" />
                <span className="text-sm text-red-700 dark:text-red-300">{t('settings_connectionFailed')}</span>
              </div>
            )}
          </div>

          {/* Privacy note */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-4">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {mode === 'local' ? t('settings_localPrivacy') : t('settings_apiPrivacy')}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function SablonlarTab(): React.JSX.Element {
  const t = useT()
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('settings_templates_title')}</h3>
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-900 p-12">
          <FileText className="h-10 w-10 text-slate-300 dark:text-slate-600 mb-3" />
          <p className="text-sm text-slate-500 dark:text-slate-400 text-center">{t('settings_templatesComing')}</p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 text-center">{t('settings_templatesDesc')}</p>
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
  const t = useT()

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('settings_display_title')}</h3>
        <div className="space-y-6">
          {/* Theme toggle */}
          <div>
            <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-2">{t('settings_theme')}</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setTheme('light')}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                  theme === 'light'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 ring-1 ring-blue-200 dark:ring-blue-800'
                    : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 '
                )}
              >
                <Sun className="h-4 w-4" />
                {t('settings_light')}
              </button>
              <button
                type="button"
                onClick={() => setTheme('dark')}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                  theme === 'dark'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 ring-1 ring-blue-200 dark:ring-blue-800'
                    : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 '
                )}
              >
                <Moon className="h-4 w-4" />
                {t('settings_dark')}
              </button>
            </div>
          </div>

          {/* Font size slider */}
          <div>
            <label htmlFor="fontSizeSlider" className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-2">
              {t('settings_fontSize', { size: fontSize })}
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
            <div className="flex justify-between text-xs text-slate-400 dark:text-slate-500 mt-1">
              <span>14px</span>
              <span>24px</span>
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
  const t = useT()

  const handlePurge = useCallback(async () => {
    setPurging(true)
    setPurgeError(null)
    setPurgeResult(null)
    try {
      const result = await apiClient.delete<PurgeResponse>('/api/v1/data/purge')
      setPurgeResult(
        t('settings_purgeResult', {
          total: result.total_deleted,
          sessions: result.deleted_sessions,
          segments: result.deleted_segments,
          reports: result.deleted_reports,
          audits: result.deleted_audit_logs,
        }),
      )
    } catch (err: unknown) {
      if (err instanceof Error) {
        setPurgeError(err.message)
      } else {
        setPurgeError(t('settings_purgeError'))
      }
    } finally {
      setPurging(false)
      setShowConfirmation(false)
    }
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">{t('settings_privacy_title')}</h3>
        <div className="space-y-4">
          {/* KVKK info */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-4 space-y-2">
            <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t('settings_kvkk_title')}</h4>
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{t('settings_kvkk_text')}</p>
          </div>

          {/* Delete all data */}
          <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/30 p-4">
            <h4 className="text-sm font-semibold text-red-800 dark:text-red-200 mb-2">{t('settings_dangerZone')}</h4>
            {!showConfirmation ? (
              <button
                type="button"
                onClick={() => setShowConfirmation(true)}
                disabled={purging}
                className="flex items-center gap-2 rounded-lg border border-red-300 dark:border-red-700 bg-white dark:bg-slate-800 px-4 py-2 text-sm font-medium text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors disabled:opacity-50"
              >
                {purging ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                {t('settings_deleteAll')}
              </button>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-red-700 dark:text-red-300">{t('settings_deleteAllConfirm')}</p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowConfirmation(false)}
                    disabled={purging}
                    className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/50  transition-colors disabled:opacity-50"
                  >
                    {t('settings_cancel')}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handlePurge()}
                    disabled={purging}
                    className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors disabled:opacity-50"
                  >
                    {purging && <Loader2 className="h-4 w-4 animate-spin" />}
                    {t('settings_deleteAllConfirmBtn')}
                  </button>
                </div>
              </div>
            )}

            {purgeResult && (
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 p-3 ring-1 ring-emerald-200 dark:ring-emerald-800">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                <p className="text-sm text-emerald-700 dark:text-emerald-300">{purgeResult}</p>
              </div>
            )}

            {purgeError && (
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 dark:bg-red-900/30 p-3 ring-1 ring-red-200 dark:ring-red-800">
                <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
                <p className="text-sm text-red-700 dark:text-red-300">{purgeError}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

const tabComponentMap: Record<TabKey, React.ComponentType> = {
  profil: ProfilTab,
  ses: SesTab,
  llm: LLMTab,
  sablonlar: SablonlarTab,
  goruntu: GoruntuTab,
  gizlilik: GizlilikTab,
}

const tabDefs: { key: TabKey; labelKey: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: 'profil', labelKey: 'settings_tab_profile', icon: User },
  { key: 'ses', labelKey: 'settings_tab_audio', icon: Mic },
  { key: 'llm', labelKey: 'settings_tab_llm', icon: BrainCircuit },
  { key: 'sablonlar', labelKey: 'settings_tab_templates', icon: FileText },
  { key: 'goruntu', labelKey: 'settings_tab_display', icon: Monitor },
  { key: 'gizlilik', labelKey: 'settings_tab_privacy', icon: Shield },
]

export function SettingsPage(): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>('profil')
  const t = useT()

  const ActiveTabComponent = tabComponentMap[activeTab]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">{t('settings_title')}</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{t('settings_subtitle')}</p>
      </div>

      <div className="flex gap-6">
        {/* Tab navigation */}
        <div className="w-48 shrink-0">
          <nav className="space-y-1">
            {tabDefs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors text-left',
                  activeTab === tab.key
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700  hover:text-slate-800 dark:hover:text-slate-100 '
                )}
              >
                <tab.icon className="h-4 w-4 shrink-0" />
                {t(tab.labelKey)}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab content */}
        <div className="flex-1 rounded-xl bg-white dark:bg-slate-800 p-6 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60">
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
