import { Menu, Bell, User, Languages } from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'
import { useAuthStore } from '../../stores/authStore'
import { useT } from '../../hooks/useT'

export function Header(): React.JSX.Element {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const locale = useUIStore((s) => s.locale)
  const setLocale = useUIStore((s) => s.setLocale)
  const user = useAuthStore((s) => s.user)
  const t = useT()

  return (
    <header className="flex items-center justify-between h-14 px-4 bg-white border-b border-slate-200">
      <button
        onClick={toggleSidebar}
        className="p-2 rounded-lg hover:bg-slate-100 text-slate-600"
      >
        <Menu className="h-5 w-5" />
      </button>

      <div className="flex items-center gap-3">
        {/* Language toggle */}
        <button
          onClick={() => setLocale(locale === 'tr' ? 'en' : 'tr')}
          title={locale === 'tr' ? 'Switch to English' : "Türkçe'ye geç"}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 transition-colors"
        >
          <Languages className="h-4 w-4" />
          {locale === 'tr' ? 'TR' : 'EN'}
        </button>

        <button className="p-2 rounded-lg hover:bg-slate-100 text-slate-600 relative">
          <Bell className="h-5 w-5" />
        </button>

        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50">
          <User className="h-4 w-4 text-slate-500" />
          <span className="text-sm text-slate-700">{user?.display_name || t('header_user')}</span>
          {user?.brans && (
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
              user.brans === 'dahiliye'
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-amber-50 text-amber-700'
            }`}>
              {user.brans === 'dahiliye' ? t('header_internalMed') : t('header_ortho')}
            </span>
          )}
          {user?.role === 'admin' && (
            <span className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium bg-purple-50 text-purple-700">
              {t('header_admin')}
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
