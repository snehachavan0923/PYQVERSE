import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { SubjectSummary } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import SubjectCard from '../components/SubjectCard'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

type SortKey = 'code' | 'name' | 'semester' | 'pyq_count'

export default function StudentSubjects() {
  const { session } = useAuth()
  const [subjects, setSubjects] = useState<SubjectSummary[] | null>(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [type, setType] = useState('')
  const [sort, setSort] = useState<SortKey>('code')

  const load = useCallback(() => {
    setError('')
    setSubjects(null)
    getWithAuth<{ subjects: SubjectSummary[] }>('/auth/student/subjects', session)
      .then((data) => setSubjects(data.subjects))
      .catch((err) => setError(errorDetail(err, 'Unable to load subjects')))
  }, [session])

  useEffect(() => {
    load()
  }, [load])

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const filtered = (subjects ?? []).filter((subject) => {
      const matchesSearch = !needle || `${subject.code} ${subject.name}`.toLowerCase().includes(needle)
      const matchesType = !type || subject.subject_type === type
      return matchesSearch && matchesType
    })
    return [...filtered].sort((a, b) => {
      if (sort === 'name') return a.name.localeCompare(b.name)
      if (sort === 'semester') return (a.semester_number ?? 0) - (b.semester_number ?? 0)
      if (sort === 'pyq_count') return b.pyq_count - a.pyq_count
      return a.code.localeCompare(b.code)
    })
  }, [subjects, search, type, sort])

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="My subjects"
        title="Enrolled subjects"
        description="Syllabus, PYQ and learning-resource availability for your enrolled subjects."
      />
      <div className="filter-bar">
        <label>
          Search subjects
          <input type="search" placeholder="Code or subject name" value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
        <label>
          Subject type
          <select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="">All types</option>
            <option value="CORE">Core</option>
            <option value="ELECTIVE">Elective</option>
          </select>
        </label>
        <label>
          Sort by
          <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
            <option value="code">Subject code</option>
            <option value="name">Subject name</option>
            <option value="semester">Semester</option>
            <option value="pyq_count">Most PYQs</option>
          </select>
        </label>
      </div>
      {error && <ErrorState message={error} onRetry={load} />}
      {!subjects && !error && <LoadingState label="Loading subjects" />}
      {subjects && (visible.length ? (
        <div className="subject-grid">
          {visible.map((subject) => <SubjectCard key={subject.id} subject={subject} />)}
        </div>
      ) : (
        <EmptyState
          title={subjects.length ? 'No subjects match your filters' : 'No subjects enrolled yet'}
          description={subjects.length ? 'Try a different search term or filter.' : 'Complete your onboarding to enroll in your semester subjects.'}
        />
      ))}
    </section>
  )
}
