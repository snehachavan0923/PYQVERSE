import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { AdminDashboardData } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import StatCard from '../components/StatCard'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

function formatWhen(value: string | null) {
  if (!value) return 'just now'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function AdminDashboard() {
  const { session } = useAuth()
  const [dashboard, setDashboard] = useState<AdminDashboardData | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    getWithAuth<AdminDashboardData>('/auth/admin/dashboard', session)
      .then(setDashboard)
      .catch((err) => setError(errorDetail(err, 'Unable to load admin dashboard')))
      .finally(() => setLoading(false))
  }, [session])

  useEffect(() => {
    load()
  }, [load])

  if (error) {
    return (
      <section className="dashboard-page">
        <PageHeader eyebrow="Administration" title="Overview" />
        <ErrorState message={error} onRetry={load} />
      </section>
    )
  }
  if (loading && !dashboard) {
    return (
      <section className="dashboard-page">
        <PageHeader eyebrow="Administration" title="Loading overview" />
        <LoadingState label="Loading administration statistics" rows={4} />
      </section>
    )
  }
  if (!dashboard) return null

  const { catalog_overview: catalog, user_overview: users, document_overview: documents } = dashboard

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Administration"
        title={`Welcome, ${dashboard.welcome_name}`}
        description="Live catalog, user and content counts from the PYQVERSE database."
        actions={
          <>
            <Link className="primary-button auth-button-link compact-button" to="/admin/pyqs">Upload PYQ</Link>
            <Link className="secondary-button auth-button-link compact-button" to="/admin/syllabus">Upload syllabus</Link>
          </>
        }
      />

      <div className="stat-grid">
        <StatCard label="Registered students" value={users.students} hint="STUDENT accounts" />
        <StatCard label="Administrators" value={users.administrators} hint="ADMIN_FACULTY accounts" />
        <StatCard label="Branches" value={catalog.branches} hint="Academic catalog" />
        <StatCard label="Academic schemes" value={catalog.academic_schemes} hint="Academic catalog" />
        <StatCard label="Semesters" value={catalog.semesters} hint="Academic catalog" />
        <StatCard label="Subjects" value={catalog.subjects} hint="Core and elective" />
        <StatCard label="Syllabus documents" value={documents.syllabus_documents} hint="Active documents" />
        <StatCard label="Question papers" value={documents.pyqs} hint="All PYQ records" />
        <StatCard label="Learning resources" value={documents.learning_resources} hint="Active resources" />
        <StatCard label="Pending review items" value={documents.pending_reviews} hint="Recorded reviews" />
      </div>

      <div className="two-column-grid">
        <article className="dashboard-card">
          <p className="eyebrow">Content overview</p>
          <h2>Uploaded documents</h2>
          <div className="detail-row"><span>Files recorded</span><strong>{documents.uploaded_documents}</strong></div>
          <div className="detail-row"><span>Syllabus documents</span><strong>{documents.syllabus_documents}</strong></div>
          <div className="detail-row"><span>Learning resources</span><strong>{documents.learning_resources}</strong></div>
          <div className="detail-row"><span>Question papers</span><strong>{documents.pyqs}</strong></div>
          <div className="form-actions" style={{ marginTop: 14 }}>
            <Link className="secondary-button auth-button-link compact-button" to="/admin/uploads">Open uploads</Link>
            <Link className="secondary-button auth-button-link compact-button" to="/admin/resources">Manage resources</Link>
          </div>
        </article>

        <article className="dashboard-card">
          <p className="eyebrow">Recent activity</p>
          <h2>Latest updates</h2>
          {dashboard.recent_activity.length ? (
            <div className="activity-list">
              {dashboard.recent_activity.map((item, index) => (
                <div className="activity-item" key={`${item.type}-${item.at}-${index}`}>
                  <span className="activity-dot" aria-hidden="true" />
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.detail ? `${item.detail} · ` : ''}{formatWhen(item.at)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No recent activity" description="Registrations and uploads will appear here as they happen." />
          )}
        </article>
      </div>
    </section>
  )
}
