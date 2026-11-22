import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { SubjectSummary } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import SubjectCard from '../components/SubjectCard'
import EmptyState from '../components/EmptyState'

export default function StudentSubjects() {
  const { session } = useAuth()
  const [subjects, setSubjects] = useState<SubjectSummary[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getWithAuth<{ subjects: SubjectSummary[] }>('/auth/student/subjects', session)
      .then((data) => setSubjects(data.subjects))
      .catch((err) => setError(errorDetail(err, 'Unable to load subjects')))
  }, [session])

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="My subjects"
        title="Enrolled subjects"
        description="Syllabus, PYQ and learning-resource availability for your enrolled subjects."
      />
      {error && <p className="form-error">{error}</p>}
      {!subjects && !error && <div className="pyq-loading">Loading subjects...</div>}
      {subjects && (subjects.length ? (
        <div className="subject-grid">
          {subjects.map((subject) => <SubjectCard key={subject.id} subject={subject} />)}
        </div>
      ) : (
        <EmptyState title="No subjects enrolled yet" description="Complete your onboarding to enroll in your semester subjects." />
      ))}
    </section>
  )
}
