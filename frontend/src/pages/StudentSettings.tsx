import { useAuth } from '../context/AuthContext'
import notifications from '../services/notification'
import PageHeader from '../components/PageHeader'
import PasswordChangeForm from '../components/PasswordChangeForm'

export default function StudentSettings() {
  const { session, logout } = useAuth()

  const confirmLogout = async () => {
    const confirmed = await notifications.confirm({
      title: 'Log out of PYQVERSE?',
      text: 'You will need to sign in again to access your workspace.',
      confirmText: 'Log out',
    })
    if (confirmed) await logout()
  }

  return (
    <section className="dashboard-page">
      <PageHeader eyebrow="Settings" title="Account settings" description="Manage your session, password and appearance preferences." />
      <article className="detail-card">
        <div className="detail-row"><span>Signed in as</span><strong>{session?.user.email ?? 'Unknown'}</strong></div>
        <div className="detail-row"><span>Email verified</span><strong>{session?.user.email_verified ? 'Yes' : 'No'}</strong></div>
        <div className="detail-row"><span>Role</span><strong>{session?.profile.role ?? 'STUDENT'}</strong></div>
      </article>
      <article className="editor-panel">
        <h2>Password</h2>
        <PasswordChangeForm />
      </article>
      <article className="detail-card">
        <h2>Appearance</h2>
        <p className="muted">Use the theme control in the top bar to switch between light and dark mode. Notifications and dialogs follow the selected theme.</p>
      </article>
      <article className="detail-card">
        <h2>Session</h2>
        <p className="muted">Sign out of this browser session.</p>
        <button className="secondary-button compact-button" type="button" onClick={() => void confirmLogout()}>
          Log out
        </button>
      </article>
    </section>
  )
}
