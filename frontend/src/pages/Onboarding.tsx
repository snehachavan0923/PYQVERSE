import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

export default function Onboarding() {
  const { session, setSession } = useAuth()
  const navigate = useNavigate()
  const [branches, setBranches] = useState<any[]>([])
  const [schemes, setSchemes] = useState<any[]>([])
  const [semesters, setSemesters] = useState<any[]>([])
  const [subjects, setSubjects] = useState<any[]>([])
  const [form, setForm] = useState({
    full_name: '', usn: '', branch_id: '', academic_scheme_id: '', semester_id: '',
    selected_elective_id: '', enrollment_year: new Date().getFullYear(),
  })
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([
      api.get('/academic/branches'),
      api.get('/academic/schemes'),
      api.get('/academic/semesters'),
      api.get('/subjects'),
    ]).then(([branchData, schemeData, semesterData, subjectData]) => {
      setBranches(branchData.data)
      setSchemes(schemeData.data)
      setSemesters(semesterData.data)
      setSubjects(subjectData.data.filter((subject: any) => subject.subject_type === 'ELECTIVE'))
    }).catch((err) => setError(err.response?.data?.detail ?? 'Unable to load academic catalog'))
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    try {
      await api.post('/auth/student/onboarding', {
        ...form,
        selected_elective_id: form.selected_elective_id || null,
      }, { headers: { Authorization: `Bearer ${session?.access_token}` } })
      if (session) setSession({ ...session, profile: { ...session.profile, onboarding_completed: true } })
      navigate('/student')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Unable to save onboarding')
    }
  }

  return (
    <section className="auth-card wide-card">
      <p className="eyebrow">Student setup</p>
      <h1>Complete your profile</h1>
      <p className="muted">This information connects you to your real academic catalog.</p>
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>Full name<input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required /></label>
          <label>USN (optional)<input value={form.usn} onChange={(event) => setForm({ ...form, usn: event.target.value })} /></label>
          <label>Department<select value={form.branch_id} onChange={(event) => setForm({ ...form, branch_id: event.target.value })} required><option value="">Select department</option>{branches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Academic scheme<select value={form.academic_scheme_id} onChange={(event) => setForm({ ...form, academic_scheme_id: event.target.value })} required><option value="">Select scheme</option>{schemes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Current semester<select value={form.semester_id} onChange={(event) => setForm({ ...form, semester_id: event.target.value })} required><option value="">Select semester</option>{semesters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Selected elective (optional)<select value={form.selected_elective_id} onChange={(event) => setForm({ ...form, selected_elective_id: event.target.value })}><option value="">No elective selected</option>{subjects.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label>
          <label>Enrollment year<input type="number" min="2020" max="2100" value={form.enrollment_year} onChange={(event) => setForm({ ...form, enrollment_year: Number(event.target.value) })} required /></label>
        </div>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button">Complete onboarding</button>
      </form>
    </section>
  )
}
