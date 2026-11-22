import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ role }: { role?: 'STUDENT' | 'ADMIN_FACULTY' }) {
  const { session, loading } = useAuth()
  if (loading) return <div className="pyq-loading">Loading...</div>
  if (!session) return <Navigate to="/login" replace />
  if (role && session.profile.role !== role) {
    return <Navigate to={session.profile.role === 'ADMIN_FACULTY' ? '/admin' : '/student'} replace />
  }
  if (role === 'STUDENT' && !session.profile.onboarding_completed) {
    return <Navigate to="/onboarding" replace />
  }
  return <Outlet />
}
