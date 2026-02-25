import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Mic,
  History,
  Settings,
  LogOut,
  FileText,
} from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'
import { useAuthStore } from '../../stores/authStore'
import { cn } from '../../lib/utils'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Ana Sayfa' },
  { path: '/session/new', icon: Mic, label: 'Yeni Gorusme' },
  { path: '/history', icon: History, label: 'Gecmis' },
  { path: '/settings', icon: Settings, label: 'Ayarlar' },
]

export function Sidebar(): React.JSX.Element {
  const location = useLocation()
  const sidebarOpen = useUIStore((s) => s.sidebarOpen)
  const logout = useAuthStore((s) => s.logout)

  return (
    <aside
      className={cn(
        'flex flex-col bg-slate-800 text-white transition-all duration-300',
        sidebarOpen ? 'w-56' : 'w-16'
      )}
    >
      <div className="flex items-center gap-2 p-4 border-b border-slate-700">
        <FileText className="h-6 w-6 text-blue-400 shrink-0" />
        {sidebarOpen && (
          <span className="text-sm font-semibold truncate">Doctor AI</span>
        )}
      </div>

      <nav className="flex-1 py-4">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          return (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                'flex items-center gap-3 px-4 py-3 text-sm transition-colors',
                isActive
                  ? 'bg-slate-700 text-white border-r-2 border-blue-400'
                  : 'text-slate-300 hover:bg-slate-700/50 hover:text-white'
              )}
            >
              <item.icon className="h-5 w-5 shrink-0" />
              {sidebarOpen && <span className="truncate">{item.label}</span>}
            </Link>
          )
        })}
      </nav>

      <button
        onClick={logout}
        className="flex items-center gap-3 px-4 py-3 text-sm text-slate-400 hover:text-white hover:bg-slate-700/50 border-t border-slate-700"
      >
        <LogOut className="h-5 w-5 shrink-0" />
        {sidebarOpen && <span>Cikis Yap</span>}
      </button>
    </aside>
  )
}
