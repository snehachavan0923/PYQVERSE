import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import { getStudentSubject, openStudentDownload, type ContentKind } from '../services/contentApi'
import notifications from '../services/notification'
import type { StudentSubjectDetail as SubjectDetail } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

type Tab = 'overview' | 'syllabus' | 'pyqs' | 'resources'

const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'syllabus', label: 'Syllabus' },
  { key: 'pyqs', label: 'Previous Year Questions' },
  { key: 'resources', label: 'Learning Resources' },
]

function statusTag(status: string) {
  const published = status === 'VERIFIED'
  return <span className={`tag ${published ? 'tag-published' : 'tag-draft'}`}>{published ? 'Published' : status}</span>
}

export default function StudentSubjectDetail() {
  const { subjectId } = useParams<{ subjectId: string }>()
  const { session } = useAuth()
  const [detail, setDetail] = useState<SubjectDetail | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Tab>('overview')
  const [downloading, setDownloading] = useState('')

  const load = useCallback(() => {
    if (!subjectId) return
    setError('')
    setDetail(null)
    getStudentSubject(session, subjectId)
      .then(setDetail)
      .catch((err) => setError(errorDetail(err, 'Unable to load this subject')))
  }, [session, subjectId])

  useEffect(() => {
    load()
  }, [load])

  const download = async (kind: ContentKind, id: string) => {
    setDownloading(id)
    try {
      const url = await openStudentDownload(session, kind, id)
      window.open(url, '_blank', 'noopener,noreferrer')
      void notifications.toast('success', 'Secure download link opened')
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The file could not be opened'))
    } finally {
      setDownloading('')
    }
  }

  if (error) {
    return (
      <section className="dashboard-page">
        <PageHeader eyebrow="Subject detail" title="Subject unavailable" actions={<Link className="secondary-button compact-button" to="/student/subjects">Back to subjects</Link>} />
        <ErrorState message={error} onRetry={load} />
      </section>
    )
  }
  if (!detail) {
    return (
      <section className="dashboard-page">
        <PageHeader eyebrow="Subject detail" title="Loading subject" />
        <LoadingState label="Loading subject detail" rows={3} />
      </section>
    )
  }

  const { subject } = detail

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow={subject.code}
        title={subject.name}
        description={`${subject.semester ?? 'Semester not set'} · ${subject.academic_scheme ?? 'Scheme not set'} · ${subject.subject_type}`}
        actions={<Link className="secondary-button compact-button" to="/student/subjects">Back to subjects</Link>}
      />

      <div className="profile-strip">
        {subject.credits !== null && <span>{subject.credits} credits</span>}
        <span>{detail.syllabus.length} syllabus document{detail.syllabus.length === 1 ? '' : 's'}</span>
        <span>{detail.pyqs.length} question paper{detail.pyqs.length === 1 ? '' : 's'}</span>
        <span>{detail.resources.length} learning resource{detail.resources.length === 1 ? '' : 's'}</span>
      </div>

      <div className="tab-bar" role="tablist" aria-label="Subject content">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            className={`tab-button${tab === item.key ? ' active' : ''}`}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <article className="detail-card">
          <h2>Subject overview</h2>
          <p className="muted">{subject.description || 'No description has been added for this subject yet.'}</p>
          <div className="detail-row"><span>Subject code</span><strong>{subject.code}</strong></div>
          <div className="detail-row"><span>Subject type</span><strong>{subject.subject_type}</strong></div>
          <div className="detail-row"><span>Credits</span><strong>{subject.credits ?? 'Not set'}</strong></div>
          <div className="detail-row"><span>Semester</span><strong>{subject.semester ?? 'Not set'}</strong></div>
          <div className="detail-row"><span>Academic scheme</span><strong>{subject.academic_scheme ?? 'Not set'}</strong></div>
        </article>
      )}

      {tab === 'syllabus' && (
        detail.syllabus.length ? (
          <div className="content-list">
            {detail.syllabus.map((document) => (
              <article className="content-item" key={document.id}>
                <div className="content-item-main">
                  <strong>{document.original_filename}</strong>
                  <div className="content-meta">
                    <span>Version {document.version}</span>
                    <span>{document.file_type.toUpperCase()}</span>
                    {statusTag(document.verification_status)}
                  </div>
                </div>
                <div className="content-item-side">
                  <button className="primary-button compact-button" type="button" disabled={downloading === document.id} onClick={() => void download('syllabus', document.id)}>
                    {downloading === document.id ? 'Opening…' : 'Download'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : <EmptyState title="No syllabus available" description="No published syllabus document exists for this subject yet." />
      )}

      {tab === 'pyqs' && (
        detail.pyqs.length ? (
          <div className="content-list">
            {detail.pyqs.map((paper) => (
              <article className="content-item" key={paper.id}>
                <div className="content-item-main">
                  <strong>{paper.title || paper.original_filename}</strong>
                  <p>{paper.description || 'No description provided.'}</p>
                  <div className="content-meta">
                    <span>{paper.exam_type}</span>
                    {paper.cie_number && <span>CIE {paper.cie_number}</span>}
                    <span>{paper.examination_year ?? 'Year not set'}</span>
                    {statusTag(paper.verification_status)}
                  </div>
                </div>
                <div className="content-item-side">
                  <button className="primary-button compact-button" type="button" disabled={downloading === paper.id} onClick={() => void download('pyq', paper.id)}>
                    {downloading === paper.id ? 'Opening…' : 'Download'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : <EmptyState title="No previous year questions" description="No published question papers exist for this subject yet." />
      )}

      {tab === 'resources' && (
        detail.resources.length ? (
          <div className="content-list">
            {detail.resources.map((resource) => (
              <article className="content-item" key={resource.id}>
                <div className="content-item-main">
                  <strong>{resource.title}</strong>
                  <p>{resource.description || 'No description provided.'}</p>
                  <div className="content-meta">
                    <span>{resource.resource_type.replaceAll('_', ' ')}</span>
                    <span>{resource.file_type.toUpperCase()}</span>
                    {statusTag(resource.verification_status)}
                  </div>
                </div>
                <div className="content-item-side">
                  <button className="primary-button compact-button" type="button" disabled={downloading === resource.id} onClick={() => void download('resource', resource.id)}>
                    {downloading === resource.id ? 'Opening…' : 'Download'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : <EmptyState title="No learning resources" description="No published learning resources exist for this subject yet." />
      )}
    </section>
  )
}
