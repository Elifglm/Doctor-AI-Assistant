import { useCallback } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  History,
  Settings,
  LogOut,
  FileText,
  ShieldCheck,
  Calendar,
} from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'
import { useAuthStore } from '../../stores/authStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useT } from '../../hooks/useT'
import { cn } from '../../lib/utils'

type NavItemDef = {
  path: string
  icon: React.ComponentType<{ className?: string }>
  labelKey: string
  adminOnly?: boolean
}

const navItemDefs: NavItemDef[] = [
  { path: '/', icon: LayoutDashboard, labelKey: 'nav_home' },
  { path: '/calendar', icon: Calendar, labelKey: 'nav_appointments' },
  { path: '/history', icon: History, labelKey: 'nav_history' },
  { path: '/settings', icon: Settings, labelKey: 'nav_settings' },
  { path: '/admin', icon: ShieldCheck, labelKey: 'nav_userMgmt', adminOnly: true },
]

export function Sidebar(): React.JSX.Element {
  const location = useLocation()
  const navigate = useNavigate()
  const sidebarOpen = useUIStore((s) => s.sidebarOpen)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const recordingState = useSessionStore((s) => s.recordingState)
  const t = useT()

  const navItems = navItemDefs.filter(
    (item) => !item.adminOnly || user?.role === 'admin'
  )

  const handleNavClick = useCallback(
    (e: React.MouseEvent, path: string) => {
      if (recordingState !== 'idle') {
        e.preventDefault()
        const confirmed = window.confirm(t('nav_confirmLeave'))
        if (confirmed) {
          useSessionStore.getState().reset()
          navigate(path)
        }
      }
    },
    [recordingState, navigate, t]
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
              {sidebarOpen && <span className="truncate">{t(item.labelKey)}</span>}
            </Link>
          )
        })}
      </nav>

      <button
        onClick={() => {
          if (recordingState !== 'idle') {
            const confirmed = window.confirm(t('nav_confirmLogout'))
            if (!confirmed) return
          }
          logout()
        }}
        className="flex items-center gap-3 px-4 py-3 text-sm text-slate-400 hover:text-white hover:bg-slate-700/50 border-t border-slate-700"
      >
        <LogOut className="h-5 w-5 shrink-0" />
        {sidebarOpen && <span>{t('nav_logout')}</span>}
      </button>
    </aside>
  )
}
