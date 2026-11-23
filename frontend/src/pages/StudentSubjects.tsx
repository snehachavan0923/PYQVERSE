import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

export default function StudentSubjects() {
  const { session } = useAuth()
  const [subjects, setSubjects] = useState<any[]>([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/auth/student/subjects', { headers: { Authorization: `Bearer ${session?.access_token}` }, params: { search } })
      .then((response) => setSubjects(response.data.items ?? []))
      .catch((err) => setError(err.response?.data?.detail ?? 'Unable to load subjects'))
  }, [session?.access_token, search])

  return (
    <section className="dashboard-shell">
      <header className="dashboard-header"><div><p className="eyebrow">Academics</p><h1>My subjects</h1></div></header>
      <article className="dashboard-card wide">
        <label>Search subjects<input value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        {error && <p className="form-error">{error}</p>}
        {!error && subjects.length === 0 && <p className="muted">No subjects match this search.</p>}
        {subjects.map((subject) => <Link className="subject-row" key={subject.id} to={`/student/subjects/${subject.id}`}><strong>{subject.code}</strong><span>{subject.name}</span></Link>)}
      </article>
    </section>
  )
}
