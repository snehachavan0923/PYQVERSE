import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

export default function AdminDashboard() {
  const { session, logout } = useAuth()
  const [dashboard, setDashboard] = useState<any>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/auth/admin/dashboard', { headers: { Authorization: `Bearer ${session?.access_token}` } })
      .then((response) => setDashboard(response.data))
      .catch((err) => setError(err.response?.data?.detail ?? 'Unable to load admin dashboard'))
  }, [session?.access_token])

  if (error) return <section className="dashboard-shell"><p className="form-error">{error}</p></section>
  if (!dashboard) return <section className="dashboard-shell"><div className="pyq-loading">Loading dashboard...</div></section>

  return (
    <section className="dashboard-shell">
      <header className="dashboard-header">
        <div><p className="eyebrow">Administration</p><h1>Welcome, {dashboard.welcome_name}</h1></div>
        <button className="text-button" onClick={logout}>Log out</button>
      </header>
      <div className="card-grid">
        <article className="dashboard-card"><p>Subjects</p><h3>{dashboard.catalog_overview.subjects}</h3></article>
        <article className="dashboard-card"><p>Semesters</p><h3>{dashboard.catalog_overview.semesters}</h3></article>
        <article className="dashboard-card"><p>Students</p><h3>{dashboard.user_overview.students}</h3></article>
        <article className="dashboard-card"><p>Administrators</p><h3>{dashboard.user_overview.administrators}</h3></article>
        <article className="dashboard-card"><p>Branches</p><h3>{dashboard.catalog_overview.branches}</h3></article>
        <article className="dashboard-card"><p>Academic schemes</p><h3>{dashboard.catalog_overview.schemes}</h3></article>
        <article className="dashboard-card"><p>Uploaded documents</p><h3>{dashboard.content_overview.uploaded_documents}</h3></article>
        <article className="dashboard-card"><p>PYQ papers</p><h3>{dashboard.content_overview.pyq_papers}</h3></article>
        <article className="dashboard-card"><p>Pending reviews</p><h3>{dashboard.content_overview.pending_reviews}</h3></article>
      </div>
      <article className="dashboard-card wide"><h2>Academic document management</h2><p className="muted">Document uploads are available in a future phase.</p></article>
    </section>
  )
}
