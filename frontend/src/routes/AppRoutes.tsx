import { Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from '../layouts/MainLayout'
import ProtectedRoute from '../components/ProtectedRoute'
import Login from '../pages/Login'
import Register from '../pages/Register'
import VerifyOtp from '../pages/VerifyOtp'
import Onboarding from '../pages/Onboarding'
import StudentDashboard from '../pages/StudentDashboard'
import AdminDashboard from '../pages/AdminDashboard'
import { useAuth } from '../context/AuthContext'

function RootRedirect() {
  const { session, loading } = useAuth()
  if (loading) return <div className="pyq-loading">Loading...</div>
  if (!session) return <Navigate to="/login" replace />
  if (session.profile.role === 'ADMIN_FACULTY') return <Navigate to="/admin" replace />
  return <Navigate to={session.profile.onboarding_completed ? '/student' : '/onboarding'} replace />
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/verify-otp" element={<VerifyOtp />} />
        <Route element={<ProtectedRoute role="STUDENT" />}>
          <Route path="/onboarding" element={<Onboarding />} />
        </Route>
        <Route element={<ProtectedRoute role="STUDENT" />}>
          <Route path="/student" element={<StudentDashboard />} />
        </Route>
        <Route element={<ProtectedRoute role="ADMIN_FACULTY" />}>
          <Route path="/admin" element={<AdminDashboard />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
