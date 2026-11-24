import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import { errorDetail, getWithAuth, patchWithAuth } from '../services/authApi'
import notifications from '../services/notification'
import type { StudentProfileData } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import PasswordChangeForm from '../components/PasswordChangeForm'
import { LoadingState, ErrorState } from '../components/PageState'

interface Option { id: string; name: string; code?: string; academic_scheme_id?: string; semester_id?: string; subject_type?: string; number?: number }

export default function StudentProfile() {
  const { session } = useAuth()
  const [profile, setProfile] = useState<StudentProfileData | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    full_name: '', usn: '', branch_id: '', academic_scheme_id: '', current_semester_id: '',
    selected_elective_id: '', enrollment_year: 2025,
  })
  const [branches, setBranches] = useState<Option[]>([])
  const [schemes, setSchemes] = useState<Option[]>([])
  const [semesters, setSemesters] = useState<Option[]>([])
  const [subjects, setSubjects] = useState<Option[]>([])

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    Promise.all([
      getWithAuth<StudentProfileData>('/auth/student/profile', session),
      api.get<Option[]>('/academic/branches'),
      api.get<Option[]>('/academic/schemes'),
      api.get<Option[]>('/academic/semesters'),
      api.get<Option[]>('/subjects'),
    ])
      .then(([profileData, branchData, schemeData, semesterData, subjectData]) => {
        setProfile(profileData)
        setForm({
          full_name: profileData.student_name,
          usn: profileData.usn ?? '',
          branch_id: profileData.branch_id ?? '',
          academic_scheme_id: profileData.academic_scheme_id ?? '',
          current_semester_id: profileData.current_semester_id ?? '',
          selected_elective_id: profileData.selected_elective_id ?? '',
          enrollment_year: profileData.enrollment_year ?? new Date().getFullYear(),
        })
        setBranches(branchData.data)
        setSchemes(schemeData.data)
        setSemesters(semesterData.data)
        setSubjects(subjectData.data.filter((subject) => subject.subject_type === 'ELECTIVE'))
      })
      .catch((err) => setError(errorDetail(err, 'Unable to load profile')))
      .finally(() => setLoading(false))
  }, [session])

  useEffect(() => {
    load()
  }, [load])

  const schemeSemesters = useMemo(
    () => semesters.filter((item) => !form.academic_scheme_id || item.academic_scheme_id === form.academic_scheme_id),
    [semesters, form.academic_scheme_id],
  )
  const eligibleElectives = useMemo(
    () => subjects.filter((item) =>
      (!form.academic_scheme_id || item.academic_scheme_id === form.academic_scheme_id) &&
      (!form.current_semester_id || item.semester_id === form.current_semester_id),
    ),
    [subjects, form.academic_scheme_id, form.current_semester_id],
  )

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (saving) return
    setError('')
    setSaving(true)
    try {
      const updated = await patchWithAuth<StudentProfileData>('/auth/student/profile', session, {
        full_name: form.full_name.trim(),
        usn: form.usn.trim() || null,
        branch_id: form.branch_id,
        academic_scheme_id: form.academic_scheme_id,
        current_semester_id: form.current_semester_id,
        selected_elective_id: form.selected_elective_id || null,
        enrollment_year: form.enrollment_year,
      })
      setProfile((current) => (current ? { ...current, ...updated } : updated))
      void notifications.toast('success', 'Profile updated')
    } catch (err) {
      setError(errorDetail(err, 'Unable to update profile'))
      void notifications.error('Profile not updated', errorDetail(err, 'Unable to update profile'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="dashboard-page">
      <PageHeader eyebrow="Profile" title="Your profile" description="Update your permitted academic details. Email, role and verification status are managed by PYQVERSE." />
      {error && !profile && <ErrorState message={error} onRetry={load} />}
      {loading && !profile && <LoadingState label="Loading profile" rows={2} />}
      {profile && (
        <>
          <article className="detail-card">
            <h2>Account identity</h2>
            <div className="detail-row"><span>Email</span><strong>{profile.email}</strong></div>
            <div className="detail-row"><span>Role</span><strong>{session?.profile.role ?? 'STUDENT'}</strong></div>
            <div className="detail-row"><span>Onboarding</span><strong>{profile.profile_completed ? 'Completed' : 'Pending'}</strong></div>
          </article>

          <form className="editor-panel" onSubmit={submit}>
            <h2>Academic details</h2>
            <div className="editor-grid">
              <label>Full name<input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required /></label>
              <label>USN<input value={form.usn} onChange={(event) => setForm({ ...form, usn: event.target.value })} placeholder="Optional" /></label>
              <label>Department<select value={form.branch_id} onChange={(event) => setForm({ ...form, branch_id: event.target.value })} required><option value="">Select department</option>{branches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Academic scheme<select value={form.academic_scheme_id} onChange={(event) => setForm({ ...form, academic_scheme_id: event.target.value, current_semester_id: '', selected_elective_id: '' })} required><option value="">Select scheme</option>{schemes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Semester<select value={form.current_semester_id} onChange={(event) => setForm({ ...form, current_semester_id: event.target.value, selected_elective_id: '' })} required><option value="">Select semester</option>{schemeSemesters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>Selected elective<select value={form.selected_elective_id} onChange={(event) => setForm({ ...form, selected_elective_id: event.target.value })}><option value="">No elective selected</option>{eligibleElectives.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label>
              <label>Enrollment year<input type="number" min="2020" max="2100" value={form.enrollment_year} onChange={(event) => setForm({ ...form, enrollment_year: Number(event.target.value) })} required /></label>
            </div>
            {error && <p className="form-error">{error}</p>}
            <div className="form-actions">
              <button className="primary-button compact-button" disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
              <button className="secondary-button compact-button" type="button" disabled={saving} onClick={load}>Reset</button>
            </div>
          </form>

          <article className="editor-panel">
            <h2>Change password</h2>
            <p className="inline-note">You will need your current password. Other sessions remain valid until they expire.</p>
            <PasswordChangeForm />
          </article>
        </>
      )}
    </section>
  )
}
