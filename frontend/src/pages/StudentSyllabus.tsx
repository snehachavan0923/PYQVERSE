import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import { listStudentSyllabus, openStudentDownload, openStudentPreview } from '../services/contentApi'
import notifications from '../services/notification'
import type { SyllabusDocumentItem } from '../types/dashboard'
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

export default function StudentSyllabus() {
  const { session } = useAuth()
  const subjects = useStudentSubjects()
  const [items, setItems] = useState<SyllabusDocumentItem[] | null>(null)
  const [error, setError] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [busy, setBusy] = useState<{ id: string; action: 'view' | 'download' } | null>(null)

  const load = useCallback(() => {
    setError('')
    setItems(null)
    listStudentSyllabus(session, { search, subject_id: subjectId || undefined })
      .then((data) => setItems(data.items))
      .catch((err) => setError(errorDetail(err, 'Unable to load syllabus documents')))
  }, [session, search, subjectId])

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
  }

  const view = async (document: SyllabusDocumentItem) => {
    const win = openPreviewWindow()
    setBusy({ id: document.id, action: 'view' })
    try {
      const url = await openStudentPreview(session, 'syllabus', document.id)
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
      if (retry) void view(document)
      return
    }
    setBusy(null)
  }

  const download = async (document: SyllabusDocumentItem) => {
    setBusy({ id: document.id, action: 'download' })
    try {
      const url = await openStudentDownload(session, 'syllabus', document.id)
      triggerDownload(url)
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The syllabus file could not be downloaded'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Syllabus"
        title="Syllabus documents"
        description="Only published syllabus documents for your enrolled subjects are listed."
      />
      <form className="filter-bar" onSubmit={submitSearch}>
        <label>
          Search
          <input type="search" placeholder="Subject or document" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} />
        </label>
        <label>
          Subject
          <select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
            <option value="">All enrolled subjects</option>
            {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.code} — {subject.name}</option>)}
          </select>
        </label>
        <button className="primary-button compact-button" type="submit">Search</button>
        <button className="secondary-button compact-button" type="button" onClick={clearFilters}>
          Clear filters
        </button>
      </form>
      {error && <ErrorState message={error} onRetry={load} />}
      {!items && !error && <LoadingState label="Loading syllabus documents" />}
      {items && (items.length ? (
        <div className="content-list">
          {items.map((document) => (
            <article className="content-item" key={document.id}>
              <div className="content-item-main">
                <strong>{document.original_filename}</strong>
                <p>{document.subject_code} — {document.subject_name}</p>
                <div className="content-meta">
                  <span>Version {document.version}</span>
                  <span>{document.file_type.toUpperCase()}</span>
                  <span className="tag tag-published">Published</span>
                </div>
              </div>
              <div className="content-item-side">
                <ContentActions
                  label={document.original_filename}
                  busy={busy?.id === document.id}
                  viewDisabled={!isPdfFile(document.file_type)}
                  viewHint={isPdfFile(document.file_type) ? 'View PDF in a new tab' : 'Preview is available for PDF documents only'}
                  onView={() => void view(document)}
                  onDownload={() => void download(document)}
                />
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState title="No syllabus found" description={search || subjectId ? 'No published syllabus matches the current filters. Draft and archived documents are not shown.' : 'Syllabus documents for your subjects have not been published yet.'} />
      ))}
    </section>
  )
}
