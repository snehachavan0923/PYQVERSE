import { useAuth } from '../context/AuthContext'
import PageHeader from '../components/PageHeader'

export default function StudentSettings() {
  const { session, logout } = useAuth()

  return (
    <section className="dashboard-page">
      <PageHeader eyebrow="Settings" title="Account settings" description="Manage your session and appearance preferences." />
      <article className="detail-card">
        <div className="detail-row">
          <span>Signed in as</span>
          <strong>{session?.user.email ?? 'Unknown'}</strong>
        </div>
        <div className="detail-row">
          <span>Email verified</span>
          <strong>{session?.user.email_verified ? 'Yes' : 'No'}</strong>
        </div>
        <div className="detail-row">
          <span>Role</span>
          <strong>{session?.profile.role ?? 'STUDENT'}</strong>
        </div>
      </article>
      <article className="detail-card">
        <h2>Appearance</h2>
        <p className="muted">Use the theme control in the top bar to switch between light and dark mode.</p>
      </article>
      <article className="detail-card">
        <h2>Session</h2>
        <p className="muted">Sign out of this browser session.</p>
        <button className="secondary-button compact-button" type="button" onClick={() => void logout()}>
          Log out
        </button>
      </article>
    </section>
  )
}
