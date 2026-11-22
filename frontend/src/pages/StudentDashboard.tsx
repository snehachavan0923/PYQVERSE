import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { StudentDashboardData } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import StatCard from '../components/StatCard'
import SubjectCard from '../components/SubjectCard'
import EmptyState from '../components/EmptyState'

export default function StudentDashboard() {
  const { session } = useAuth()
  const [dashboard, setDashboard] = useState<StudentDashboardData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getWithAuth<StudentDashboardData>('/auth/student/dashboard', session)
      .then(setDashboard)
      .catch((err) => setError(errorDetail(err, 'Unable to load dashboard')))
  }, [session])

  if (error) return <section className="dashboard-page"><p className="form-error">{error}</p></section>
  if (!dashboard) return <section className="dashboard-page"><div className="pyq-loading">Loading dashboard...</div></section>

  const { profile, academic_overview: overview } = dashboard

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Student workspace"
        title={`Welcome, ${dashboard.welcome_name}`}
        description="Your semester, subjects and available academic material at a glance."
      />

      <div className="profile-strip">
        <span>{profile.department ?? 'Department not set'}</span>
        <span>{profile.semester ?? 'Semester not set'}</span>
        <span>{profile.academic_scheme ?? 'Scheme not set'}</span>
        <span>USN: {profile.usn ?? 'Not provided'}</span>
        <span>Elective: {profile.selected_elective ?? 'None selected'}</span>
      </div>

      <div className="stat-grid">
        <StatCard label="Current semester" value={overview.current_semester ?? 'Not set'} />
        <StatCard label="Enrolled subjects" value={overview.enrolled_subjects} />
        <StatCard label="Subjects with syllabus" value={overview.subjects_with_syllabus} />
        <StatCard label="Subjects with PYQs" value={overview.subjects_with_pyqs} />
      </div>

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Academic overview</p>
            <h2>Subject cards</h2>
          </div>
        </div>
        {dashboard.subjects.length ? (
          <div className="subject-grid">
            {dashboard.subjects.map((subject) => (
              <SubjectCard key={subject.id} subject={subject} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="No subjects enrolled yet"
            description="Complete your onboarding or contact your department to be enrolled in subjects."
          />
        )}
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Learning resources</p>
            <h2>Resource availability</h2>
          </div>
        </div>
        <EmptyState
          title="No resources uploaded yet"
          description="Learning resources will appear here once they are uploaded and verified by faculty."
        />
      </section>
    </section>
  )
}
