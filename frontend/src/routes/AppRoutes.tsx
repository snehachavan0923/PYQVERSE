import { Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from '../layouts/MainLayout'
import DashboardLayout from '../layouts/DashboardLayout'
import ProtectedRoute from '../components/ProtectedRoute'
import Login from '../pages/Login'
import Register from '../pages/Register'
import ForgotPassword from '../pages/ForgotPassword'
import ResetPassword from '../pages/ResetPassword'
import Onboarding from '../pages/Onboarding'
import StudentDashboard from '../pages/StudentDashboard'
import StudentSubjects from '../pages/StudentSubjects'
import StudentSubjectDetail from '../pages/StudentSubjectDetail'
import StudentSyllabus from '../pages/StudentSyllabus'
import StudentPyqs from '../pages/StudentPyqs'
import StudentResources from '../pages/StudentResources'
import StudentProfile from '../pages/StudentProfile'
import StudentSettings from '../pages/StudentSettings'
import AdminDashboard from '../pages/AdminDashboard'
import AdminAcademic from '../pages/AdminAcademic'
import AdminUsers from '../pages/AdminUsers'
import AdminProfile from '../pages/AdminProfile'
import AdminSettings from '../pages/AdminSettings'
import AdminContentManager from '../pages/AdminContentManager'
import AdminUploads from '../pages/AdminUploads'
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
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route element={<ProtectedRoute role="STUDENT" />}>
          <Route path="/onboarding" element={<Onboarding />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>

      <Route element={<ProtectedRoute role="STUDENT" requireOnboarding />}>
        <Route element={<DashboardLayout role="STUDENT" />}>
          <Route path="/student" element={<StudentDashboard />} />
          <Route path="/student/subjects" element={<StudentSubjects />} />
          <Route path="/student/subjects/:subjectId" element={<StudentSubjectDetail />} />
          <Route path="/student/syllabus" element={<StudentSyllabus />} />
          <Route path="/student/pyqs" element={<StudentPyqs />} />
          <Route path="/student/resources" element={<StudentResources />} />
          <Route path="/student/profile" element={<StudentProfile />} />
          <Route path="/student/settings" element={<StudentSettings />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute role="ADMIN_FACULTY" />}>
        <Route element={<DashboardLayout role="ADMIN_FACULTY" />}>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/academic" element={<AdminAcademic />} />
          <Route path="/admin/users" element={<AdminUsers />} />
          <Route path="/admin/syllabus" element={<AdminContentManager kind="syllabus" />} />
          <Route path="/admin/pyqs" element={<AdminContentManager kind="pyq" />} />
          <Route path="/admin/resources" element={<AdminContentManager kind="resource" />} />
          <Route path="/admin/uploads" element={<AdminUploads />} />
          <Route path="/admin/profile" element={<AdminProfile />} />
          <Route path="/admin/settings" element={<AdminSettings />} />
        </Route>
      </Route>
    </Routes>
  )
}
