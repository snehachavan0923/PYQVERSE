import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { SyllabusDocumentItem } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'

export default function StudentSyllabus() {
  const { session } = useAuth()
  const [documents, setDocuments] = useState<SyllabusDocumentItem[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getWithAuth<{ documents: SyllabusDocumentItem[] }>('/auth/student/syllabus', session)
      .then((data) => setDocuments(data.documents))
      .catch((err) => setError(errorDetail(err, 'Unable to load syllabus documents')))
  }, [session])

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Syllabus"
        title="Syllabus documents"
        description="Only syllabus documents uploaded for your enrolled subjects are listed."
      />
      {error && <p className="form-error">{error}</p>}
      {!documents && !error && <div className="pyq-loading">Loading syllabus...</div>}
      {documents && (documents.length ? (
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Subject</th>
                <th>Version</th>
                <th>Document</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.id}>
                  <td>
                    <strong>{document.subject_code}</strong>
                    <span className="table-subtext">{document.subject_name}</span>
                  </td>
                  <td>{document.version}</td>
                  <td>{document.original_filename}</td>
                  <td>{document.verification_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="No syllabus uploaded yet" description="Syllabus documents for your subjects have not been uploaded yet." />
      ))}
    </section>
  )
}
