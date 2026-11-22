import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { StudentProfileData } from '../types/dashboard'
import PageHeader from '../components/PageHeader'

function Detail({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="detail-row">
      <span>{label}</span>
      <strong>{value ?? 'Not set'}</strong>
    </div>
  )
}

export default function StudentProfile() {
  const { session } = useAuth()
  const [profile, setProfile] = useState<StudentProfileData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getWithAuth<StudentProfileData>('/auth/student/profile', session)
      .then(setProfile)
      .catch((err) => setError(errorDetail(err, 'Unable to load profile')))
  }, [session])

  return (
    <section className="dashboard-page">
      <PageHeader eyebrow="Profile" title="Your profile" description="Your PYQVERSE student identity and academic configuration." />
      {error && <p className="form-error">{error}</p>}
      {!profile && !error && <div className="pyq-loading">Loading profile...</div>}
      {profile && (
        <article className="detail-card">
          <Detail label="Full name" value={profile.student_name} />
          <Detail label="Email" value={profile.email} />
          <Detail label="USN" value={profile.usn} />
          <Detail label="Department" value={profile.branch} />
          <Detail label="Academic scheme" value={profile.academic_scheme} />
          <Detail label="Current semester" value={profile.semester} />
          <Detail label="Selected elective" value={profile.selected_elective} />
          <Detail label="Enrollment year" value={profile.enrollment_year} />
          <Detail label="Onboarding" value={profile.profile_completed ? 'Completed' : 'Pending'} />
        </article>
      )}
    </section>
  )
}
