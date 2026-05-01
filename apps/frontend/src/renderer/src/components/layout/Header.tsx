import { Menu, User, Languages, Sun, Moon } from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'
import { useAuthStore } from '../../stores/authStore'
import { useT } from '../../hooks/useT'

export function Header(): React.JSX.Element {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const locale = useUIStore((s) => s.locale)
  const setLocale = useUIStore((s) => s.setLocale)
  const theme = useUIStore((s) => s.theme)
  const setTheme = useUIStore((s) => s.setTheme)
  const user = useAuthStore((s) => s.user)
  const t = useT()

  return (
    <header className="flex items-center justify-between h-14 px-4 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
      <button
        onClick={toggleSidebar}
        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700  text-slate-600 dark:text-slate-300"
      >
        <Menu className="h-5 w-5" />
      </button>

      <div className="flex items-center gap-3">
        {/* Theme toggle */}
        <button
          type="button"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
          aria-label={theme === 'dark' ? 'Light mode' : 'Dark mode'}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>

        {/* Language toggle */}
        <button
          onClick={() => setLocale(locale === 'tr' ? 'en' : 'tr')}
          title={locale === 'tr' ? 'Switch to English' : "Türkçe'ye geç"}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 px-2.5 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700  transition-colors"
        >
          <Languages className="h-4 w-4" />
          {locale === 'tr' ? 'TR' : 'EN'}
        </button>

        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 dark:bg-slate-900">
          <User className="h-4 w-4 text-slate-500 dark:text-slate-400" />
          <span className="text-sm text-slate-700 dark:text-slate-200">{user?.display_name || t('header_user')}</span>
          {user?.brans && (
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
              user.brans === 'dahiliye'
                ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                : 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
            }`}>
              {user.brans === 'dahiliye' ? t('header_internalMed') : t('header_ortho')}
            </span>
          )}
          {user?.role === 'admin' && (
            <span className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">
              {t('header_admin')}
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
