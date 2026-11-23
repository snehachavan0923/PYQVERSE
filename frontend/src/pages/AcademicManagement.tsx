import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

export default function AcademicManagement() {
  const { session } = useAuth()
  const [subjects, setSubjects] = useState<any[]>([])
  const [branches, setBranches] = useState<any[]>([])
  const [schemes, setSchemes] = useState<any[]>([])
  const [semesters, setSemesters] = useState<any[]>([])
  const [error, setError] = useState('')

  const load = async () => {
    setError('')
    try {
      const headers = { Authorization: `Bearer ${session?.access_token}` }
      const [subjectData, branchData, schemeData, semesterData] = await Promise.all([
        api.get('/admin/academic/subjects', { headers }),
        api.get('/academic/branches'),
        api.get('/academic/schemes'),
        api.get('/academic/semesters'),
      ])
      setSubjects(subjectData.data.items ?? [])
      setBranches(branchData.data)
      setSchemes(schemeData.data)
      setSemesters(semesterData.data)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Unable to load academic records')
    }
  }

  useEffect(() => { void load() }, [session?.access_token])

  return (
    <section className="dashboard-shell">
      <header className="dashboard-header"><div><p className="eyebrow">Academic management</p><h1>Catalog</h1></div></header>
      {error && <article className="dashboard-card"><p className="form-error">{error}</p><button className="secondary-button" onClick={load}>Retry</button></article>}
      {!error && !subjects.length && <article className="dashboard-card"><p className="muted">No subjects are available.</p></article>}
      {subjects.length > 0 && (
        <article className="dashboard-card wide">
          <div className="subject-list">{subjects.map((subject) => <div key={subject.id}><strong>{subject.code}</strong><span>{subject.name} · {subject.subject_type}</span></div>)}</div>
        </article>
      )}
      <div className="card-grid">
        <article className="dashboard-card"><p>Branches</p><h3>{branches.length}</h3></article>
        <article className="dashboard-card"><p>Academic schemes</p><h3>{schemes.length}</h3></article>
        <article className="dashboard-card"><p>Semesters</p><h3>{semesters.length}</h3></article>
      </div>
    </section>
  )
}
