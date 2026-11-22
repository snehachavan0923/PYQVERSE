import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

export default function StudentDashboard() {
  const { session, logout } = useAuth()
  const [dashboard, setDashboard] = useState<any>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/auth/student/dashboard', { headers: { Authorization: `Bearer ${session?.access_token}` } })
      .then((response) => setDashboard(response.data))
      .catch((err) => setError(err.response?.data?.detail ?? 'Unable to load dashboard'))
  }, [session?.access_token])

  if (error) return <section className="dashboard-shell"><p className="form-error">{error}</p></section>
  if (!dashboard) return <section className="dashboard-shell"><div className="pyq-loading">Loading dashboard...</div></section>

  return (
    <section className="dashboard-shell">
      <header className="dashboard-header">
        <div><p className="eyebrow">Student workspace</p><h1>Welcome, {dashboard.welcome_name}</h1></div>
        <button className="text-button" onClick={logout}>Log out</button>
      </header>
      <div className="card-grid">
        <article className="dashboard-card"><p>Department</p><h3>{dashboard.profile.department ?? 'Not set'}</h3></article>
        <article className="dashboard-card"><p>Current semester</p><h3>{dashboard.profile.semester ?? 'Not set'}</h3></article>
        <article className="dashboard-card"><p>Selected elective</p><h3>{dashboard.profile.selected_elective ?? 'None selected'}</h3></article>
      </div>
      <article className="dashboard-card wide"><h2>Enrolled subjects</h2>
        {dashboard.enrolled_subjects.length ? <div className="subject-list">{dashboard.enrolled_subjects.map((subject: any) => <div key={subject.id}><strong>{subject.code}</strong><span>{subject.name}</span></div>)}</div> : <p className="muted">No subjects are enrolled yet.</p>}
      </article>
      <article className="dashboard-card wide"><h2>Academic preparation</h2><p className="muted">Learning modules will appear here in a future phase.</p></article>
    </section>
  )
}
