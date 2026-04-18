import { Menu, Bell, User } from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'
import { useAuthStore } from '../../stores/authStore'

export function Header(): React.JSX.Element {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const user = useAuthStore((s) => s.user)

  return (
    <header className="flex items-center justify-between h-14 px-4 bg-white border-b border-slate-200">
      <button
        onClick={toggleSidebar}
        className="p-2 rounded-lg hover:bg-slate-100 text-slate-600"
      >
        <Menu className="h-5 w-5" />
      </button>

      <div className="flex items-center gap-3">
        <button className="p-2 rounded-lg hover:bg-slate-100 text-slate-600 relative">
          <Bell className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50">
          <User className="h-4 w-4 text-slate-500" />
          <span className="text-sm text-slate-700">{user?.display_name || 'Kullanici'}</span>
          {user?.brans && (
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
              user.brans === 'dahiliye'
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-amber-50 text-amber-700'
            }`}>
              {user.brans === 'dahiliye' ? 'Dahiliye' : 'Ortopedi'}
            </span>
          )}
          {user?.role === 'admin' && (
            <span className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium bg-purple-50 text-purple-700">
              Admin
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
