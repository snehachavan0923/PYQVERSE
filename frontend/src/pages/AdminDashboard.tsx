import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { AdminDashboardData } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import StatCard from '../components/StatCard'
import EmptyState from '../components/EmptyState'

export default function AdminDashboard() {
  const { session } = useAuth()
  const [dashboard, setDashboard] = useState<AdminDashboardData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getWithAuth<AdminDashboardData>('/auth/admin/dashboard', session)
      .then(setDashboard)
      .catch((err) => setError(errorDetail(err, 'Unable to load admin dashboard')))
  }, [session])

  if (error) return <section className="dashboard-page"><p className="form-error">{error}</p></section>
  if (!dashboard) return <section className="dashboard-page"><div className="pyq-loading">Loading dashboard...</div></section>

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Administration"
        title={`Welcome, ${dashboard.welcome_name}`}
        description="Live catalog, user and document counts from the PYQVERSE database."
      />

      <div className="stat-grid">
        <StatCard label="Registered students" value={dashboard.user_overview.students} />
        <StatCard label="Subjects" value={dashboard.catalog_overview.subjects} />
        <StatCard label="Semesters" value={dashboard.catalog_overview.semesters} />
        <StatCard label="Uploaded documents" value={dashboard.document_overview.uploaded_documents} />
        <StatCard label="Question papers" value={dashboard.document_overview.pyqs} />
        <StatCard label="Pending review items" value={dashboard.document_overview.pending_reviews} />
      </div>

      <div className="two-column-grid">
        <article className="dashboard-card">
          <p className="eyebrow">Catalog</p>
          <h2>Academic structure</h2>
          <div className="detail-row"><span>Branches</span><strong>{dashboard.catalog_overview.branches}</strong></div>
          <div className="detail-row"><span>Academic schemes</span><strong>{dashboard.catalog_overview.academic_schemes}</strong></div>
          <div className="detail-row"><span>Administrators</span><strong>{dashboard.user_overview.administrators}</strong></div>
        </article>
        <article className="dashboard-card">
          <p className="eyebrow">Content management</p>
          <h2>Upload workflows</h2>
          <EmptyState
            title="Upload workflows are not enabled yet"
            description="Syllabus, PYQ and learning-resource management screens are prepared but document upload and OCR processing arrive in a later phase."
          />
        </article>
      </div>
    </section>
  )
}
