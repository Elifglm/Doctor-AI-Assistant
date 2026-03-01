import { useCallback } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
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
import { useSessionStore } from '../../stores/sessionStore'
import { cn } from '../../lib/utils'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Ana Sayfa' },
  { path: '/session/new', icon: Mic, label: 'Yeni Görüşme' },
  { path: '/history', icon: History, label: 'Geçmiş' },
  { path: '/settings', icon: Settings, label: 'Ayarlar' },
]

export function Sidebar(): React.JSX.Element {
  const location = useLocation()
  const navigate = useNavigate()
  const sidebarOpen = useUIStore((s) => s.sidebarOpen)
  const logout = useAuthStore((s) => s.logout)
  const recordingState = useSessionStore((s) => s.recordingState)

  const handleNavClick = useCallback(
    (e: React.MouseEvent, path: string) => {
      if (recordingState !== 'idle') {
        e.preventDefault()
        const confirmed = window.confirm(
          'Aktif bir kayıt var. Sayfadan ayrılmak istediğinize emin misiniz? Kayıt durdurulacak.'
        )
        if (confirmed) {
          useSessionStore.getState().reset()
          navigate(path)
        }
      }
    },
    [recordingState, navigate]
  )

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
              onClick={(e) => handleNavClick(e, item.path)}
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
        onClick={() => {
          if (recordingState !== 'idle') {
            const confirmed = window.confirm(
              'Aktif bir kayıt var. Çıkış yapmak istediğinize emin misiniz? Kayıt durdurulacak.'
            )
            if (!confirmed) return
          }
          logout()
        }}
        className="flex items-center gap-3 px-4 py-3 text-sm text-slate-400 hover:text-white hover:bg-slate-700/50 border-t border-slate-700"
      >
        <LogOut className="h-5 w-5 shrink-0" />
        {sidebarOpen && <span>Çıkış Yap</span>}
      </button>
    </aside>
  )
}
