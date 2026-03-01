import { HashRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLayout } from './components/layout/AppLayout'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { PreSessionPage } from './pages/PreSessionPage'
import { LiveSessionPage } from './pages/LiveSessionPage'
import { ProcessingPage } from './pages/ProcessingPage'
import { ReportReviewPage } from './pages/ReportReviewPage'
import { SessionHistoryPage } from './pages/SessionHistoryPage'
import { SettingsPage } from './pages/SettingsPage'

// TODO [S7 - Deferred to Production]: Role-based UI access controls.
// Currently this prototype only has a single "admin" user with the "doctor" role.
// For production deployment, implement role-based route guards here:
//   - "doctor" role: full access to sessions, recordings, reports
//   - "nurse" role: read-only access to session history, no report approval
//   - "admin" role: access to settings, user management, data purge
// The backend already returns `user.role` in the JWT payload.
// Use a <ProtectedRoute requiredRole="..."> wrapper component around each <Route>.

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30000,
    },
  },
})

function App(): React.JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/session/new" element={<PreSessionPage />} />
            <Route path="/session/:id/live" element={<LiveSessionPage />} />
            <Route path="/session/:id/processing" element={<ProcessingPage />} />
            <Route path="/session/:id/review" element={<ReportReviewPage />} />
            <Route path="/history" element={<SessionHistoryPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </HashRouter>
    </QueryClientProvider>
  )
}

export default App
