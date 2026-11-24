import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import { friendlyError } from '../services/errors'
import notifications from '../services/notification'
import { useAuth } from '../context/AuthContext'
import { LoadingState, ErrorState } from '../components/PageState'

const CURRENT_YEAR = new Date().getFullYear()

interface BranchOption { id: string; name: string; code: string }
interface SchemeOption { id: string; name: string; code: string }
interface SemesterOption { id: string; name: string; number: number; academic_scheme_id?: string }
interface SubjectOption { id: string; code: string; name: string; subject_type: string; academic_scheme_id?: string; semester_id?: string }

export default function Onboarding() {
  const { session, setSession } = useAuth()
  const navigate = useNavigate()
  const [branches, setBranches] = useState<BranchOption[]>([])
  const [schemes, setSchemes] = useState<SchemeOption[]>([])
  const [semesters, setSemesters] = useState<SemesterOption[]>([])
  const [subjects, setSubjects] = useState<SubjectOption[]>([])
  const [catalogError, setCatalogError] = useState('')
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [form, setForm] = useState({
    full_name: '', usn: '', branch_id: '', academic_scheme_id: '', semester_id: '',
    selected_elective_id: '', enrollment_year: CURRENT_YEAR,
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const loadCatalog = () => {
    setCatalogLoading(true)
    setCatalogError('')
    Promise.all([
      api.get<BranchOption[]>('/academic/branches'),
      api.get<SchemeOption[]>('/academic/schemes'),
      api.get<SemesterOption[]>('/academic/semesters'),
      api.get<SubjectOption[]>('/subjects'),
    ])
      .then(([branchData, schemeData, semesterData, subjectData]) => {
        setBranches(branchData.data)
        setSchemes(schemeData.data)
        setSemesters(semesterData.data)
        setSubjects(subjectData.data.filter((subject) => subject.subject_type === 'ELECTIVE'))
      })
      .catch((err) => setCatalogError(friendlyError(err, 'Unable to load academic catalog')))
      .finally(() => setCatalogLoading(false))
  }

  useEffect(() => {
    loadCatalog()
  }, [])

  const schemeSemesters = useMemo(
    () => semesters.filter((item) => !form.academic_scheme_id || item.academic_scheme_id === form.academic_scheme_id),
    [semesters, form.academic_scheme_id],
  )
  const eligibleElectives = useMemo(
    () => subjects.filter((item) =>
      (!form.academic_scheme_id || item.academic_scheme_id === form.academic_scheme_id) &&
      (!form.semester_id || item.semester_id === form.semester_id),
    ),
    [subjects, form.academic_scheme_id, form.semester_id],
  )

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (loading) return
    setError('')
    setLoading(true)
    try {
      await api.post('/auth/student/onboarding', {
        ...form,
        selected_elective_id: form.selected_elective_id || null,
      }, { headers: { Authorization: `Bearer ${session?.access_token}` } })
      if (session) setSession({ ...session, profile: { ...session.profile, onboarding_completed: true } })
      void notifications.toast('success', 'Profile setup complete')
      navigate('/student', { replace: true })
    } catch (err) {
      setError(friendlyError(err, 'Unable to save onboarding'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="auth-card wide-card">
      <p className="eyebrow">Student setup</p>
      <h1>Complete your profile</h1>
      <p className="muted">This information connects you to your real academic catalog.</p>
      {catalogLoading && <LoadingState label="Loading academic catalog" rows={2} />}
      {catalogError && <ErrorState message={catalogError} onRetry={loadCatalog} />}
      {!catalogLoading && !catalogError && (
        <form onSubmit={submit}>
          <div className="form-grid">
            <label>Full name<input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required /></label>
            <label>USN (optional)<input value={form.usn} onChange={(event) => setForm({ ...form, usn: event.target.value })} /></label>
            <label>Department<select value={form.branch_id} onChange={(event) => setForm({ ...form, branch_id: event.target.value })} required><option value="">Select department</option>{branches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label>Academic scheme<select value={form.academic_scheme_id} onChange={(event) => setForm({ ...form, academic_scheme_id: event.target.value, semester_id: '', selected_elective_id: '' })} required><option value="">Select scheme</option>{schemes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label>Current semester<select value={form.semester_id} onChange={(event) => setForm({ ...form, semester_id: event.target.value, selected_elective_id: '' })} required><option value="">Select semester</option>{schemeSemesters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label>Selected elective (optional)<select value={form.selected_elective_id} onChange={(event) => setForm({ ...form, selected_elective_id: event.target.value })}><option value="">No elective selected</option>{eligibleElectives.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label>
            <label>Enrollment year<input type="number" min="2020" max="2100" value={form.enrollment_year} onChange={(event) => setForm({ ...form, enrollment_year: Number(event.target.value) })} required /></label>
          </div>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button" disabled={loading}>{loading ? 'Saving…' : 'Complete onboarding'}</button>
        </form>
      )}
    </section>
  )
}
