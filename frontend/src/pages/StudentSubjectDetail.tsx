import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import {
  getStudentSubject,
  openStudentDownload,
  openStudentPreview,
  type ContentKind,
} from '../services/contentApi'
import notifications from '../services/notification'
import type { StudentSubjectDetail as SubjectDetail } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import ContentActions from '../components/ContentActions'
import { LoadingState, ErrorState } from '../components/PageState'
import {
  closePreviewWindow,
  isPdfFile,
  loadPreview,
  openPreviewWindow,
  triggerDownload,
} from '../utils/documentActions'
import { detectResourceSource, parseYouTubeUrl } from '../utils/resourceUtils'

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
  const [busy, setBusy] = useState<{ id: string; action: 'view' | 'download' } | null>(null)

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

  const view = async (kind: ContentKind, id: string) => {
    const win = openPreviewWindow()
    setBusy({ id, action: 'view' })
    try {
      const url = await openStudentPreview(session, kind, id)
      if (!loadPreview(win, url)) {
        void notifications.error(
          'Preview blocked',
          'Allow pop-ups for PYQVERSE to preview this PDF, or use Download instead.',
        )
      }
    } catch (err) {
      closePreviewWindow(win)
      setBusy(null)
      const retry = await notifications.retryError(
        'Preview unavailable',
        errorDetail(err, 'The preview link could not be created. It may have expired.'),
      )
      if (retry) void view(kind, id)
      return
    }
    setBusy(null)
  }

  const download = async (kind: ContentKind, id: string) => {
    setBusy({ id, action: 'download' })
    try {
      const url = await openStudentDownload(session, kind, id)
      triggerDownload(url)
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The file could not be downloaded'))
    } finally {
      setBusy(null)
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
            id={`tab-${item.key}`}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            aria-controls={`panel-${item.key}`}
            className={`tab-button${tab === item.key ? ' active' : ''}`}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div role="tabpanel" id="panel-overview" aria-labelledby="tab-overview" tabIndex={0}>
          <article className="detail-card">
            <h2>Subject overview</h2>
            <p className="muted">{subject.description || 'No description has been added for this subject yet.'}</p>
            <div className="detail-row"><span>Subject code</span><strong>{subject.code}</strong></div>
            <div className="detail-row"><span>Subject type</span><strong>{subject.subject_type}</strong></div>
            <div className="detail-row"><span>Credits</span><strong>{subject.credits ?? 'Not set'}</strong></div>
            <div className="detail-row"><span>Semester</span><strong>{subject.semester ?? 'Not set'}</strong></div>
            <div className="detail-row"><span>Academic scheme</span><strong>{subject.academic_scheme ?? 'Not set'}</strong></div>
          </article>
        </div>
      )}

      {tab === 'syllabus' && (
        <div role="tabpanel" id="panel-syllabus" aria-labelledby="tab-syllabus" tabIndex={0}>
          {detail.syllabus.length ? (
            <div className="content-list">
              {detail.syllabus.map((document) => (
                <article className="content-item" key={document.id}>
                  <div className="content-item-main">
                    <strong>{document.original_filename}</strong>
                    <div className="content-meta">
                      <span>Version {document.version}</span>
                      <span>{(document.file_type || '').toUpperCase()}</span>
                      {statusTag(document.verification_status)}
                    </div>
                  </div>
                  <div className="content-item-side">
                    <ContentActions
                      withLabels
                      label={document.original_filename || 'Syllabus'}
                      busy={busy?.id === document.id}
                      viewDisabled={!isPdfFile(document.file_type || '')}
                      viewHint={isPdfFile(document.file_type || '') ? 'View PDF in a new tab' : 'Preview is available for PDF documents only'}
                      onView={() => void view('syllabus', document.id)}
                      onDownload={() => void download('syllabus', document.id)}
                    />
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="No syllabus available" description="No published syllabus document exists for this subject yet." />
          )}
        </div>
      )}

      {tab === 'pyqs' && (
        <div role="tabpanel" id="panel-pyqs" aria-labelledby="tab-pyqs" tabIndex={0}>
          {detail.pyqs.length ? (
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
                    <ContentActions
                      withLabels
                      label={paper.title || paper.original_filename || 'Question Paper'}
                      busy={busy?.id === paper.id}
                      onView={() => void view('pyq', paper.id)}
                      onDownload={() => void download('pyq', paper.id)}
                    />
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="No previous year questions" description="No published question papers exist for this subject yet." />
          )}
        </div>
      )}

      {tab === 'resources' && (
        <div role="tabpanel" id="panel-resources" aria-labelledby="tab-resources" tabIndex={0}>
          {detail.resources.length ? (
            <div className="content-list">
              {detail.resources.map((resource) => {
                const source = detectResourceSource(resource)
                const hasFile = source === 'FILE' || source === 'BOTH' || Boolean(resource.file_size)
                const yt = resource.external_url ? parseYouTubeUrl(resource.external_url) : null

                return (
                  <article className="content-item" key={resource.id}>
                    {yt?.thumbnailUrl && (
                      <div className="resource-card-thumb">
                        <img src={yt.thumbnailUrl} alt="Video thumbnail" />
                        <div className="resource-play-overlay">
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                            <polygon points="5 3 19 12 5 21 5 3" />
                          </svg>
                        </div>
                      </div>
                    )}
                    <div className="content-item-main">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                        <strong>{resource.title}</strong>
                        <span className={`tag tag-source-${source.toLowerCase()}`}>
                          {source === 'FILE' ? '📄 File' : source === 'LINK' ? '🔗 Link' : '📄+🔗 File & Link'}
                        </span>
                      </div>
                      <p>{resource.description || 'No description provided.'}</p>
                      {resource.external_url && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', marginTop: '2px' }}>
                          <span style={{ color: 'var(--muted)' }}>URL:</span>
                          <a
                            href={resource.external_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: 'var(--primary)', textDecoration: 'underline', overflowWrap: 'anywhere' }}
                          >
                            {resource.link_title || resource.external_url}
                          </a>
                        </div>
                      )}
                      <div className="content-meta">
                        <span>{resource.resource_type.replaceAll('_', ' ')}</span>
                        {resource.unit_title && <span>Unit {resource.unit_number ?? ''}: {resource.unit_title}</span>}
                        {hasFile && resource.file_type && <span>{resource.file_type.toUpperCase()}</span>}
                        {statusTag(resource.verification_status)}
                      </div>
                    </div>
                    <div className="content-item-side">
                      <div className="row-actions">
                        {resource.external_url && (
                          <a
                            className="secondary-button compact-button resource-link-btn"
                            href={resource.external_url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {yt?.isYouTube ? '▶ Watch Video' : '↗ Open Resource'}
                          </a>
                        )}
                        {hasFile && (
                          <ContentActions
                            withLabels
                            label={resource.title}
                            busy={busy?.id === resource.id}
                            viewDisabled={!isPdfFile(resource.file_type || '')}
                            viewHint={isPdfFile(resource.file_type || '') ? 'View PDF in a new tab' : 'Preview is available for PDF documents only'}
                            onView={() => void view('resource', resource.id)}
                            onDownload={() => void download('resource', resource.id)}
                          />
                        )}
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          ) : (
            <EmptyState title="No learning resources" description="No published learning resources exist for this subject yet." />
          )}
        </div>
      )}
    </section>
  )
}
