import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { StudentDashboardData } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import StatCard from '../components/StatCard'
import SubjectCard from '../components/SubjectCard'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object'
}

function isStudentDashboard(value: unknown): value is StudentDashboardData {
  return (
    isRecord(value) &&
    typeof value.welcome_name === 'string' &&
    isRecord(value.profile) &&
    isRecord(value.academic_overview) &&
    Array.isArray(value.subjects)
  )
}

const QUICK_LINKS = [
  { label: 'My subjects', hint: 'Enrolled semester subjects', to: '/student/subjects' },
  { label: 'Syllabus', hint: 'Published syllabus documents', to: '/student/syllabus' },
  { label: 'Question papers', hint: 'Previous year questions', to: '/student/pyqs' },
  { label: 'Learning resources', hint: 'Notes and study material', to: '/student/resources' },
]

export default function StudentDashboard() {
  const { session } = useAuth()
  const [dashboard, setDashboard] = useState<StudentDashboardData | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    getWithAuth<StudentDashboardData>('/auth/student/dashboard', session)
      .then((data) => {
        if (!isStudentDashboard(data)) {
          setError('The server returned an incomplete dashboard. Please retry.')
          return
        }
        setDashboard(data)
      })
      .catch((err) => setError(errorDetail(err, 'Unable to load dashboard')))
      .finally(() => setLoading(false))
  }, [session])

  useEffect(() => {
    load()
  }, [load])

  if (error) {
    return (
      <section className="dashboard-page">
        <PageHeader eyebrow="Student workspace" title="Dashboard" />
        <ErrorState message={error} onRetry={load} />
      </section>
    )
  }
  if (loading && !dashboard) {
    return (
      <section className="dashboard-page">
        <PageHeader eyebrow="Student workspace" title="Loading your workspace" />
        <LoadingState label="Loading your dashboard" rows={4} />
      </section>
    )
  }
  if (!dashboard) {
    return (
      <section className="dashboard-page">
        <PageHeader eyebrow="Student workspace" title="Dashboard" />
        <ErrorState message="The dashboard response was empty. Please retry." onRetry={load} />
      </section>
    )
  }

  const { profile, academic_overview: overview } = dashboard
  const progress = dashboard.progress
  const progressAvailable = Boolean(dashboard.academic_preparation?.progress_available && progress)

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Student workspace"
        title={`Welcome, ${dashboard.welcome_name}`}
        description="Your semester, subjects and available academic material at a glance."
        actions={<Link className="primary-button auth-button-link" to="/student/subjects">Browse subjects</Link>}
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
        <StatCard label="Enrolled subjects" value={overview.enrolled_subjects ?? 0} />
        <StatCard label="Subjects with syllabus" value={overview.subjects_with_syllabus ?? 0} />
        <StatCard label="Subjects with PYQs" value={overview.subjects_with_pyqs ?? 0} />
        <StatCard label="Question papers" value={overview.pyq_count ?? 0} />
        <StatCard label="Learning resources" value={overview.learning_resource_count ?? 0} />
      </div>

      {progressAvailable && progress && (
        <section className="section-block">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Study progress</p>
              <h2>Your recorded topic activity</h2>
            </div>
          </div>
          <div className="stat-grid">
            <StatCard label="Topics started" value={progress.started_topics} />
            <StatCard label="Topics completed" value={progress.completed_topics} />
            <StatCard label="Topics bookmarked" value={progress.bookmarked_topics} />
          </div>
        </section>
      )}

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Academic overview</p>
            <h2>Your subjects</h2>
          </div>
          <Link to="/student/subjects" className="text-button">View all subjects</Link>
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

      <div className="two-column-grid">
        <article className="dashboard-card">
          <p className="eyebrow">Question papers</p>
          <h2>{overview.pyq_count ?? 0} published paper{(overview.pyq_count ?? 0) === 1 ? '' : 's'}</h2>
          <p className="muted">
            {overview.subjects_with_pyqs ?? 0} of your enrolled subjects have published question papers.
          </p>
          <div className="form-actions" style={{ marginTop: 16 }}>
            <Link className="secondary-button auth-button-link compact-button" to="/student/pyqs">
              Open question papers
            </Link>
          </div>
        </article>

        <article className="dashboard-card">
          <p className="eyebrow">Learning resources</p>
          <h2>{overview.learning_resource_count ?? 0} resource{(overview.learning_resource_count ?? 0) === 1 ? '' : 's'}</h2>
          <p className="muted">
            {overview.learning_resources_available
              ? 'Published notes, study material and reference documents are available for your subjects.'
              : 'Learning resources will appear here once faculty publish and verify them.'}
          </p>
          <div className="form-actions" style={{ marginTop: 16 }}>
            <Link className="secondary-button auth-button-link compact-button" to="/student/resources">
              Open resources
            </Link>
          </div>
        </article>
      </div>

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Quick navigation</p>
            <h2>Jump to your academic sections</h2>
          </div>
        </div>
        <div className="quick-grid">
          {QUICK_LINKS.map((link) => (
            <Link className="quick-link" key={link.to} to={link.to}>
              <strong>{link.label}</strong>
              <span>{link.hint}</span>
              <span className="quick-link-arrow" aria-hidden="true">→</span>
            </Link>
          ))}
        </div>
      </section>
    </section>
  )
}
