import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import notifications from '../services/notification'

interface ProtectedRouteProps {
  role?: 'STUDENT' | 'ADMIN_FACULTY'
  requireOnboarding?: boolean
}

function RouteLoading() {
  return (
    <div className="route-loading" role="status" aria-live="polite">
      <span className="route-loading-badge">PYQ</span>
      <span className="sr-only">Restoring your session…</span>
    </div>
  )
}

export default function ProtectedRoute({ role, requireOnboarding = false }: ProtectedRouteProps) {
  const { session, loading } = useAuth()
  const location = useLocation()
  const actualRole = session?.profile.role
  const denied = Boolean(session && role && actualRole && actualRole !== role)

  useEffect(() => {
    if (denied && actualRole === 'STUDENT' && role === 'ADMIN_FACULTY') {
      void notifications.warning(
        'Access denied',
        'Administrator pages are restricted to ADMIN_FACULTY accounts.',
      )
    }
  }, [denied, actualRole, role, location.pathname])

  if (loading) return <RouteLoading />
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (role && actualRole !== role) {
    return <Navigate to={actualRole === 'ADMIN_FACULTY' ? '/admin' : '/student'} replace />
  }
  if (role === 'STUDENT' && requireOnboarding && !session.profile.onboarding_completed) {
    return <Navigate to="/onboarding" replace />
  }
  return <Outlet />
}
