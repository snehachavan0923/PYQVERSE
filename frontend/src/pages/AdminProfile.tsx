import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth, patchWithAuth } from '../services/authApi'
import notifications from '../services/notification'
import PageHeader from '../components/PageHeader'
import { ErrorState, LoadingState } from '../components/PageState'

interface AdminProfileData {
  id: string
  full_name: string
  email: string
  role: string
  account_status: string
  email_verified: boolean
  last_login_at: string | null
}

function Detail({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="detail-row">
      <span>{label}</span>
      <strong>{value ?? 'Not set'}</strong>
    </div>
  )
}

function formatDate(value: string | null) {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

export default function AdminProfile() {
  const { session } = useAuth()
  const [profile, setProfile] = useState<AdminProfileData | null>(null)
  const [error, setError] = useState('')
  const [fullName, setFullName] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getWithAuth<AdminProfileData>('/auth/admin/profile', session)
      .then((data) => {
        setProfile(data)
        setFullName(data.full_name)
      })
      .catch((err) => setError(errorDetail(err, 'Unable to load admin profile')))
  }, [session])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!profile || saving) return
    const name = fullName.trim()
    if (name.length < 2) {
      void notifications.error('Name required', 'Enter your full name.')
      return
    }
    setSaving(true)
    try {
      const updated = await patchWithAuth<AdminProfileData>('/auth/admin/profile', session, {
        full_name: name,
      })
      setProfile(updated)
      setFullName(updated.full_name)
      void notifications.toast('success', 'Profile updated')
    } catch (err) {
      void notifications.error('Update failed', errorDetail(err, 'The profile could not be updated'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="dashboard-page">
      <PageHeader eyebrow="Profile" title="Administrator profile" description="Your ADMIN_FACULTY identity and account status." />
      {error && <ErrorState message={error} />}
      {!profile && !error && <LoadingState label="Loading profile" rows={3} />}
      {profile && (
        <div className="two-column-grid">
          <form className="editor-panel" onSubmit={submit}>
            <h2>Account details</h2>
            <label>
              Full name
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                required
                minLength={2}
                maxLength={200}
              />
            </label>
            <p className="form-hint">Your email and role are managed by the institution and cannot be edited here.</p>
            <div className="form-actions">
              <button className="primary-button compact-button" disabled={saving}>
                {saving ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          </form>
          <article className="detail-card">
            <Detail label="Full name" value={profile.full_name} />
            <Detail label="Email" value={profile.email} />
            <Detail label="Role" value={profile.role} />
            <Detail label="Account status" value={profile.account_status} />
            <Detail label="Email verified" value={profile.email_verified ? 'Yes' : 'No'} />
            <Detail label="Last login" value={formatDate(profile.last_login_at)} />
          </article>
        </div>
      )}
    </section>
  )
}
