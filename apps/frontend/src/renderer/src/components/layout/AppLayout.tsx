import { useState, useCallback, useEffect } from 'react'
import { Outlet, Navigate, useNavigate } from 'react-router-dom'
import { AlertTriangle, UserPlus, X } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { useAuthStore } from '../../stores/authStore'
import { useInactivityTimeout } from '../../hooks/useInactivityTimeout'
import { useT } from '../../hooks/useT'
import { apiClient } from '../../services/apiClient'

function InactivityWarningDialog({ onDismiss }: { onDismiss: () => void }): React.JSX.Element {
  const t = useT()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-xl bg-white dark:bg-slate-800 p-6 shadow-xl ring-1 ring-slate-200/60 dark:ring-slate-700/60">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/40">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
          </div>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{t('layout_sessionTimeout')}</h2>
        </div>
        <p className="mb-6 text-sm text-slate-600 dark:text-slate-300">{t('layout_sessionTimeoutMsg')}</p>
        <button
          type="button"
          onClick={onDismiss}
          className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
        >
          {t('layout_continueSession')}
        </button>
      </div>
    </div>
  )
}

export function AppLayout(): React.JSX.Element {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const t = useT()

  const [showWarning, setShowWarning] = useState(false)
  const [newDoctorCount, setNewDoctorCount] = useState(0)
  const [showDoctorBanner, setShowDoctorBanner] = useState(false)

  const handleLogout = useCallback(() => {
    logout()
  }, [logout])

  const handleWarningChange = useCallback((visible: boolean) => {
    setShowWarning(visible)
  }, [])

  const { resetTimers: resetInactivityTimers } = useInactivityTimeout({
    enabled: isAuthenticated,
    onLogout: handleLogout,
    onWarningChange: handleWarningChange,
  })

  const handleDismissWarning = useCallback(() => {
    setShowWarning(false)
    resetInactivityTimers()
  }, [resetInactivityTimers])

  // Startup check: admin kullanicisi icin OpenEMR'de yeni doktor var mi
  useEffect(() => {
    if (!isAuthenticated || user?.role !== 'admin') return

    const checkNewDoctors = async () => {
      try {
        const data = await apiClient.get<{ new_count: number }>('/api/v1/admin/openemr-doctors')
        if (data.new_count > 0) {
          setNewDoctorCount(data.new_count)
          setShowDoctorBanner(true)
        }
      } catch {
        // OpenEMR unavailable — skip silently
      }
    }
    void checkNewDoctors()
  }, [isAuthenticated, user?.role])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-900">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header />
        {/* New doctor notification banner */}
        {showDoctorBanner && newDoctorCount > 0 && (
          <div className="flex items-center justify-between bg-amber-50 dark:bg-amber-900/30 border-b border-amber-200 dark:border-amber-800 px-4 py-2.5">
            <div className="flex items-center gap-2">
              <UserPlus className="h-4 w-4 text-amber-600" />
              <span className="text-sm text-amber-800 dark:text-amber-200">
                {t('layout_newDoctorsFound', { count: newDoctorCount })}
              </span>
              <button
                onClick={() => {
                  setShowDoctorBanner(false)
                  navigate('/admin')
                }}
                className="ml-1 rounded bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-700 transition-colors"
              >
                {t('layout_assignRole')}
              </button>
            </div>
            <button
              onClick={() => setShowDoctorBanner(false)}
              className="rounded p-1 text-amber-400 hover:text-amber-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      {showWarning && (
        <InactivityWarningDialog onDismiss={handleDismissWarning} />
      )}
      <ConfirmDialog />
    </div>
  )
}
