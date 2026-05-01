import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Stethoscope, Loader2, Languages, Sun, Moon } from 'lucide-react'
import { apiClient } from '../services/apiClient'
import { useAuthStore } from '../stores/authStore'
import { useUIStore } from '../stores/uiStore'
import { useT } from '../hooks/useT'

interface LoginResponse {
  access_token: string
  expires_in: number
  user: {
    id: number
    username: string
    display_name: string
    role: string
    brans: string
  }
}

export function LoginPage(): React.JSX.Element {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const locale = useUIStore((s) => s.locale)
  const setLocale = useUIStore((s) => s.setLocale)
  const theme = useUIStore((s) => s.theme)
  const setTheme = useUIStore((s) => s.setTheme)
  const t = useT()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const response = await apiClient.post<LoginResponse>('/api/v1/auth/login', {
        username,
        password,
      })
      setAuth(response.access_token, response.user, response.expires_in)
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError(t('login_error'))
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-900">
      {/* Top-right toggles: theme + language */}
      <div className="absolute right-4 top-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
          aria-label={theme === 'dark' ? 'Light mode' : 'Dark mode'}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={() => setLocale(locale === 'tr' ? 'en' : 'tr')}
          title={locale === 'tr' ? 'Switch to English' : "Türkçe'ye geç"}
          aria-label={locale === 'tr' ? 'Switch to English' : "Türkçe'ye geç"}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
        >
          <Languages className="h-4 w-4" />
          {locale === 'tr' ? 'TR' : 'EN'}
        </button>
      </div>

      <div className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-800 p-8 shadow-lg ring-1 ring-slate-200/60 dark:ring-slate-700/60">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-900/30">
            <Stethoscope className="h-7 w-7 text-blue-600" />
          </div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Doctor AI Assistant</h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="username" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">
              {t('login_username')}
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t('login_usernamePlaceholder')}
              required
              className="w-full rounded-lg border border-slate-300 dark:border-slate-600 px-3.5 py-2.5 text-sm text-slate-800 dark:text-slate-100 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200">
              {t('login_password')}
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('login_passwordPlaceholder')}
              required
              className="w-full rounded-lg border border-slate-300 dark:border-slate-600 px-3.5 py-2.5 text-sm text-slate-800 dark:text-slate-100 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500/50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('login_submit')}
          </button>

          {error && (
            <p className="text-center text-sm text-red-600">{error}</p>
          )}
        </form>
      </div>
    </div>
  )
}
