import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

export default function ProfilePage() {
  const { session } = useAuth()
  const [profile, setProfile] = useState<any>(null)
  useEffect(() => {
    const role = session?.profile.role
    if (role === 'STUDENT') {
      api.get('/auth/student/profile', { headers: { Authorization: `Bearer ${session?.access_token}` } })
        .then((response) => setProfile(response.data))
        .catch(() => setProfile(null))
    } else {
      setProfile({ email: session?.user.email, full_name: session?.user.email, role })
    }
  }, [session?.access_token, session?.profile.role])
  return (
    <section className="dashboard-shell">
      <header className="dashboard-header"><div><p className="eyebrow">Account</p><h1>Profile</h1></div></header>
      <article className="dashboard-card wide">
        <h2>{profile?.full_name ?? session?.user.email}</h2>
        <p className="muted">{profile?.email ?? session?.user.email}</p>
        {profile?.usn && <p className="muted">USN: {profile.usn}</p>}
        {profile?.branch && <p className="muted">Branch: {profile.branch}</p>}
        {profile?.semester && <p className="muted">Semester: {profile.semester}</p>}
        {profile?.academic_scheme && <p className="muted">Academic scheme: {profile.academic_scheme}</p>}
        {profile?.selected_elective && <p className="muted">Elective: {profile.selected_elective}</p>}
        <p className="muted">Role: {session?.profile.role}</p>
      </article>
    </section>
  )
}
