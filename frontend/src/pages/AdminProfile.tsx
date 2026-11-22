import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import PageHeader from '../components/PageHeader'

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

export default function AdminProfile() {
  const { session } = useAuth()
  const [profile, setProfile] = useState<AdminProfileData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getWithAuth<AdminProfileData>('/auth/admin/profile', session)
      .then(setProfile)
      .catch((err) => setError(errorDetail(err, 'Unable to load admin profile')))
  }, [session])

  return (
    <section className="dashboard-page">
      <PageHeader eyebrow="Profile" title="Administrator profile" description="Your ADMIN_FACULTY identity and account status." />
      {error && <p className="form-error">{error}</p>}
      {!profile && !error && <div className="pyq-loading">Loading profile...</div>}
      {profile && (
        <article className="detail-card">
          <Detail label="Full name" value={profile.full_name} />
          <Detail label="Email" value={profile.email} />
          <Detail label="Role" value={profile.role} />
          <Detail label="Account status" value={profile.account_status} />
          <Detail label="Email verified" value={profile.email_verified ? 'Yes' : 'No'} />
          <Detail label="Last login" value={profile.last_login_at} />
        </article>
      )}
    </section>
  )
}
