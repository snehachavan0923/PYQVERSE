import { Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from '../layouts/MainLayout'
import ProtectedRoute from '../components/ProtectedRoute'
import Login from '../pages/Login'
import Register from '../pages/Register'
import VerifyOtp from '../pages/VerifyOtp'
import Onboarding from '../pages/Onboarding'
import StudentDashboard from '../pages/StudentDashboard'
import AdminDashboard from '../pages/AdminDashboard'
import AcademicManagement from '../pages/AcademicManagement'
import UserManagement from '../pages/UserManagement'
import AdminDocumentPage from '../pages/AdminDocumentPage'
import StudentSubjects from '../pages/StudentSubjects'
import SubjectDetail from '../pages/SubjectDetail'
import StudentContentPage from '../pages/StudentContentPage'
import ProfilePage from '../pages/ProfilePage'
import SettingsPage from '../pages/SettingsPage'
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
          <Route path="/student/subjects" element={<StudentSubjects />} />
          <Route path="/student/subjects/:subjectId" element={<SubjectDetail />} />
          <Route path="/student/syllabus" element={<StudentContentPage kind="syllabus" />} />
          <Route path="/student/pyqs" element={<StudentContentPage kind="pyqs" />} />
          <Route path="/student/resources" element={<StudentContentPage kind="resources" />} />
          <Route path="/student/profile" element={<ProfilePage />} />
          <Route path="/student/settings" element={<SettingsPage />} />
        </Route>
        <Route element={<ProtectedRoute role="ADMIN_FACULTY" />}>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/academic" element={<AcademicManagement />} />
          <Route path="/admin/users" element={<UserManagement />} />
          <Route path="/admin/syllabus" element={<AdminDocumentPage kind="syllabus" />} />
          <Route path="/admin/pyqs" element={<AdminDocumentPage kind="pyqs" />} />
          <Route path="/admin/resources" element={<AdminDocumentPage kind="resources" />} />
          <Route path="/admin/uploads" element={<AdminDocumentPage kind="uploads" />} />
          <Route path="/admin/profile" element={<ProfilePage />} />
          <Route path="/admin/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
