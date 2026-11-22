import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { QuestionPaperItem } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'

export default function StudentPyqs() {
  const { session } = useAuth()
  const [papers, setPapers] = useState<QuestionPaperItem[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getWithAuth<{ question_papers: QuestionPaperItem[] }>('/auth/student/pyqs', session)
      .then((data) => setPapers(data.question_papers))
      .catch((err) => setError(errorDetail(err, 'Unable to load previous year questions')))
  }, [session])

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Previous Year Questions"
        title="Question papers"
        description="Actual question papers uploaded for your enrolled subjects."
      />
      {error && <p className="form-error">{error}</p>}
      {!papers && !error && <div className="pyq-loading">Loading question papers...</div>}
      {papers && (papers.length ? (
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Subject</th>
                <th>Exam</th>
                <th>CIE</th>
                <th>Year</th>
              </tr>
            </thead>
            <tbody>
              {papers.map((paper) => (
                <tr key={paper.id}>
                  <td>
                    <strong>{paper.subject_code}</strong>
                    <span className="table-subtext">{paper.subject_name}</span>
                  </td>
                  <td>{paper.exam_type}</td>
                  <td>{paper.cie_number ?? '—'}</td>
                  <td>{paper.examination_year ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="No PYQs uploaded yet" description="Previous year question papers for your subjects have not been uploaded yet." />
      ))}
    </section>
  )
}
