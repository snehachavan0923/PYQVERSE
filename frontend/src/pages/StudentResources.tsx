import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import { listStudentResources, openStudentDownload, openStudentPreview } from '../services/contentApi'
import notifications from '../services/notification'
import type { LearningResourceItem } from '../types/dashboard'
import { useStudentSubjects } from '../hooks/useStudentSubjects'
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

const RESOURCE_TYPES = [
  ['', 'All resource types'],
  ['NOTES', 'Notes'],
  ['STUDY_MATERIAL', 'Study material'],
  ['REFERENCE', 'Reference documents'],
  ['IMPORTANT_QUESTIONS', 'Important questions'],
  ['OTHER', 'Other'],
] as const

const SOURCE_FILTERS = [
  ['', 'All sources'],
  ['FILE', 'Files only'],
  ['LINK', 'External links only'],
  ['BOTH', 'Both file & link'],
] as const

export default function StudentResources() {
  const { session } = useAuth()
  const subjects = useStudentSubjects()
  const [items, setItems] = useState<LearningResourceItem[] | null>(null)
  const [error, setError] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [resourceType, setResourceType] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [busy, setBusy] = useState<{ id: string; action: 'view' | 'download' } | null>(null)

  const load = useCallback(() => {
    setError('')
    setItems(null)
    listStudentResources(session, {
      search,
      subject_id: subjectId || undefined,
      resource_type: resourceType || undefined,
    })
      .then((data) => setItems(data.items))
      .catch((err) => setError(errorDetail(err, 'Unable to load learning resources')))
  }, [session, search, subjectId, resourceType])

  useEffect(() => {
    load()
  }, [load])

  const submitSearch = (event: FormEvent) => {
    event.preventDefault()
    setSearch(searchInput.trim())
  }

  const clearFilters = () => {
    setSearchInput('')
    setSearch('')
    setSubjectId('')
    setResourceType('')
    setSourceFilter('')
  }

  const filteredItems = useMemo(() => {
    if (!items) return null
    if (!sourceFilter) return items
    return items.filter((res) => {
      const src = detectResourceSource(res)
      return src === sourceFilter
    })
  }, [items, sourceFilter])

  const view = async (resource: LearningResourceItem) => {
    const win = openPreviewWindow()
    setBusy({ id: resource.id, action: 'view' })
    try {
      const url = await openStudentPreview(session, 'resource', resource.id)
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
      if (retry) void view(resource)
      return
    }
    setBusy(null)
  }

  const download = async (resource: LearningResourceItem) => {
    setBusy({ id: resource.id, action: 'download' })
    try {
      const url = await openStudentDownload(session, 'resource', resource.id)
      triggerDownload(url)
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The learning resource could not be downloaded'))
    } finally {
      setBusy(null)
    }
  }

  const filtered = Boolean(search || subjectId || resourceType || sourceFilter)

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Learning resources"
        title="Learning Resources"
        description="Published notes, study material, video links and reference documents for your subjects."
      />
      <form className="filter-bar" onSubmit={submitSearch}>
        <label>
          Search
          <input type="search" placeholder="Title or description" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} />
        </label>
        <label>
          Subject
          <select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
            <option value="">All enrolled subjects</option>
            {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.code} — {subject.name}</option>)}
          </select>
        </label>
        <label>
          Resource type
          <select value={resourceType} onChange={(event) => setResourceType(event.target.value)}>
            {RESOURCE_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>
          Source
          <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
            {SOURCE_FILTERS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <button className="primary-button compact-button" type="submit">Search</button>
        <button className="secondary-button compact-button" type="button" onClick={clearFilters}>
          Clear filters
        </button>
      </form>
      {error && <ErrorState message={error} onRetry={load} />}
      {!items && !error && <LoadingState label="Loading learning resources" />}
      {filteredItems && (filteredItems.length ? (
        <div className="content-list">
          {filteredItems.map((resource) => {
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
                  <p>{resource.description || `${resource.subject_code} — ${resource.subject_name}`}</p>
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
                    <span>{resource.subject_code}</span>
                    <span>{resource.resource_type.replaceAll('_', ' ')}</span>
                    {resource.unit_title && <span>Unit {resource.unit_number ?? ''}: {resource.unit_title}</span>}
                    {hasFile && resource.file_type && <span>{resource.file_type.toUpperCase()}</span>}
                    {hasFile && resource.original_filename && <span>{resource.original_filename}</span>}
                    <span className="tag tag-published">Published</span>
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
                        onView={() => void view(resource)}
                        onDownload={() => void download(resource)}
                      />
                    )}
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      ) : (
        <EmptyState title="No learning resources found" description={filtered ? 'No published resources match the current filters. Draft and archived resources are not shown.' : 'Learning resources for your subjects have not been published yet.'} />
      ))}
    </section>
  )
}
