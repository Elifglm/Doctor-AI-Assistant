import { useState, useCallback } from 'react'
import { Outlet, Navigate } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { useAuthStore } from '../../stores/authStore'
import { useInactivityTimeout } from '../../hooks/useInactivityTimeout'

// TODO [S7 - Production]: Role-based access control should be implemented here.
// Currently the prototype has a single admin/doctor user.  For production,
// gate routes based on `user.role` (e.g. "doctor", "nurse", "admin") and
// hide/show sidebar links accordingly.

function InactivityWarningDialog({ onDismiss }: { onDismiss: () => void }): React.JSX.Element {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl ring-1 ring-slate-200/60">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-100">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
          </div>
          <h2 className="text-lg font-semibold text-slate-800">Oturum Zaman Aşımı</h2>
        </div>
        <p className="mb-6 text-sm text-slate-600">
          Uzun süredir işlem yapmadınız. 5 dakika içinde otomatik olarak çıkış yapılacaktır.
          Devam etmek için herhangi bir tuşa basın veya fareyi hareket ettirin.
        </p>
        <button
          type="button"
          onClick={onDismiss}
          className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
        >
          Oturuma Devam Et
        </button>
      </div>
    </div>
  )
}

export function AppLayout(): React.JSX.Element {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const logout = useAuthStore((s) => s.logout)

  const [showWarning, setShowWarning] = useState(false)

  const handleLogout = useCallback(() => {
    logout()
  }, [logout])

  const handleWarningChange = useCallback((visible: boolean) => {
    setShowWarning(visible)
  }, [])

  useInactivityTimeout({
    enabled: isAuthenticated,
    onLogout: handleLogout,
    onWarningChange: handleWarningChange,
  })

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      {showWarning && (
        <InactivityWarningDialog onDismiss={() => setShowWarning(false)} />
      )}
    </div>
  )
}
