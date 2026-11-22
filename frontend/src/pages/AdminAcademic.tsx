import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'

interface BranchItem { id: string; name: string; code: string; active: boolean }
interface SchemeItem { id: string; name: string; code: string; active: boolean }
interface SemesterItem { id: string; number: number; name: string; active: boolean }
interface SubjectItem {
  id: string
  code: string
  name: string
  subject_type: string
  credits: number | null
  semester_id: string
  academic_scheme_id: string
  active: boolean
}
interface ElectiveItem {
  basket_id: string
  basket_name: string
  subject_id: string
  subject_code: string
  subject_name: string
  active: boolean
}

export default function AdminAcademic() {
  const { session } = useAuth()
  const [data, setData] = useState<{
    branches: BranchItem[]
    schemes: SchemeItem[]
    semesters: SemesterItem[]
    subjects: SubjectItem[]
    electives: ElectiveItem[]
  } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([
      getWithAuth<BranchItem[]>('/auth/admin/academic/branches', session),
      getWithAuth<SchemeItem[]>('/auth/admin/academic/schemes', session),
      getWithAuth<SemesterItem[]>('/auth/admin/academic/semesters', session),
      getWithAuth<SubjectItem[]>('/auth/admin/academic/subjects', session),
      getWithAuth<ElectiveItem[]>('/auth/admin/academic/elective-options', session),
    ])
      .then(([branches, schemes, semesters, subjects, electives]) => {
        setData({ branches, schemes, semesters, subjects, electives })
      })
      .catch((err) => setError(errorDetail(err, 'Unable to load academic catalog')))
  }, [session])

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Academic management"
        title="Academic catalog"
        description="Read-only view of the existing branches, schemes, semesters, subjects and elective options."
      />
      {error && <p className="form-error">{error}</p>}
      {!data && !error && <div className="pyq-loading">Loading academic catalog...</div>}
      {data && (
        <>
          <div className="two-column-grid">
            <article className="dashboard-card">
              <p className="eyebrow">Branches</p>
              <h2>Branches</h2>
              {data.branches.length ? (
                <div className="compact-list">
                  {data.branches.map((item) => (
                    <div key={item.id}><strong>{item.code}</strong><span>{item.name}</span></div>
                  ))}
                </div>
              ) : <EmptyState title="No branches" description="No branches are configured." />}
            </article>
            <article className="dashboard-card">
              <p className="eyebrow">Schemes</p>
              <h2>Academic schemes</h2>
              {data.schemes.length ? (
                <div className="compact-list">
                  {data.schemes.map((item) => (
                    <div key={item.id}><strong>{item.code}</strong><span>{item.name}</span></div>
                  ))}
                </div>
              ) : <EmptyState title="No schemes" description="No academic schemes are configured." />}
            </article>
            <article className="dashboard-card">
              <p className="eyebrow">Semesters</p>
              <h2>Semesters</h2>
              {data.semesters.length ? (
                <div className="compact-list">
                  {data.semesters.map((item) => (
                    <div key={item.id}><strong>{item.number}</strong><span>{item.name}</span></div>
                  ))}
                </div>
              ) : <EmptyState title="No semesters" description="No semesters are configured." />}
            </article>
            <article className="dashboard-card">
              <p className="eyebrow">Electives</p>
              <h2>Elective options</h2>
              {data.electives.length ? (
                <div className="compact-list">
                  {data.electives.map((item) => (
                    <div key={`${item.basket_id}-${item.subject_id}`}>
                      <strong>{item.subject_code}</strong>
                      <span>{item.subject_name} · {item.basket_name}</span>
                    </div>
                  ))}
                </div>
              ) : <EmptyState title="No elective options" description="No elective baskets are configured." />}
            </article>
          </div>

          <article className="table-card">
            <h2>Subjects</h2>
            {data.subjects.length ? (
              <table>
                <thead>
                  <tr><th>Code</th><th>Name</th><th>Type</th><th>Credits</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {data.subjects.map((subject) => (
                    <tr key={subject.id}>
                      <td><strong>{subject.code}</strong></td>
                      <td>{subject.name}</td>
                      <td>{subject.subject_type}</td>
                      <td>{subject.credits ?? '—'}</td>
                      <td>{subject.active ? 'Active' : 'Inactive'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <EmptyState title="No subjects" description="No subjects are configured." />}
          </article>
        </>
      )}
    </section>
  )
}
