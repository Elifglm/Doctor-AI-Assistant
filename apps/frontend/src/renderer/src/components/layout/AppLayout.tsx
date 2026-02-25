import { Outlet, Navigate } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { useAuthStore } from '../../stores/authStore'

export function AppLayout(): React.JSX.Element {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

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
    </div>
  )
}
