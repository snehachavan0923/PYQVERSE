import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import { listStudentResources, openStudentDownload } from '../services/contentApi'
import notifications from '../services/notification'
import type { LearningResourceItem } from '../types/dashboard'
import { useStudentSubjects } from '../hooks/useStudentSubjects'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

const RESOURCE_TYPES = [
  ['', 'All resource types'],
  ['NOTES', 'Notes'],
  ['STUDY_MATERIAL', 'Study material'],
  ['REFERENCE', 'Reference documents'],
  ['IMPORTANT_QUESTIONS', 'Important questions'],
  ['OTHER', 'Other'],
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
  const [downloading, setDownloading] = useState('')

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

  const download = async (resource: LearningResourceItem) => {
    setDownloading(resource.id)
    try {
      const url = await openStudentDownload(session, 'resource', resource.id)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The learning resource could not be opened'))
    } finally {
      setDownloading('')
    }
  }

  const filtered = Boolean(search || subjectId || resourceType)

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Learning resources"
        title="Learning resources"
        description="Published notes, study material and reference documents for your subjects."
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
        <button className="primary-button" type="submit">Search</button>
      </form>
      {error && <ErrorState message={error} onRetry={load} />}
      {!items && !error && <LoadingState label="Loading learning resources" />}
      {items && (items.length ? (
        <div className="content-list">
          {items.map((resource) => (
            <article className="content-item" key={resource.id}>
              <div className="content-item-main">
                <strong>{resource.title}</strong>
                <p>{resource.description || `${resource.subject_code} — ${resource.subject_name}`}</p>
                <div className="content-meta">
                  <span>{resource.subject_code}</span>
                  <span>{resource.resource_type.replaceAll('_', ' ')}</span>
                  <span>{resource.file_type.toUpperCase()}</span>
                  <span className="tag tag-published">Published</span>
                </div>
              </div>
              <div className="content-item-side">
                <button className="primary-button compact-button" type="button" disabled={downloading === resource.id} onClick={() => void download(resource)}>
                  {downloading === resource.id ? 'Opening…' : 'Download'}
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState title="No learning resources found" description={filtered ? 'No published resources match the current filters.' : 'Learning resources for your subjects have not been published yet.'} />
      ))}
    </section>
  )
}
