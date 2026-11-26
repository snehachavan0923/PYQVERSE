import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import { listStudentPyqs, openStudentDownload, openStudentPreview } from '../services/contentApi'
import notifications from '../services/notification'
import type { QuestionPaperItem } from '../types/dashboard'
import { useStudentSubjects } from '../hooks/useStudentSubjects'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import ContentActions from '../components/ContentActions'
import { LoadingState, ErrorState } from '../components/PageState'
import {
  closePreviewWindow,
  loadPreview,
  openPreviewWindow,
  triggerDownload,
} from '../utils/documentActions'

const CURRENT_YEAR = new Date().getFullYear()
const YEARS = Array.from({ length: 11 }).map((_, index) => CURRENT_YEAR - index)

function PaperIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 3h6l4 4v12a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v5h5M10 13h4M10 17h3" />
    </svg>
  )
}

export default function StudentPyqs() {
  const { session } = useAuth()
  const subjects = useStudentSubjects()
  const [items, setItems] = useState<QuestionPaperItem[] | null>(null)
  const [error, setError] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [year, setYear] = useState('')
  const [examType, setExamType] = useState('')
  const [busy, setBusy] = useState<{ id: string; action: 'view' | 'download' } | null>(null)

  const load = useCallback(() => {
    setError('')
    setItems(null)
    listStudentPyqs(session, {
      search,
      subject_id: subjectId || undefined,
      year: year ? Number(year) : undefined,
      exam_type: examType || undefined,
    })
      .then((data) => setItems(data.items))
      .catch((err) => setError(errorDetail(err, 'Unable to load previous year questions')))
  }, [session, search, subjectId, year, examType])

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
    setYear('')
    setExamType('')
  }

  const view = async (paper: QuestionPaperItem) => {
    const win = openPreviewWindow()
    setBusy({ id: paper.id, action: 'view' })
    try {
      const url = await openStudentPreview(session, 'pyq', paper.id)
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
      if (retry) void view(paper)
      return
    }
    setBusy(null)
  }

  const download = async (paper: QuestionPaperItem) => {
    setBusy({ id: paper.id, action: 'download' })
    try {
      const url = await openStudentDownload(session, 'pyq', paper.id)
      triggerDownload(url)
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The question paper could not be downloaded'))
    } finally {
      setBusy(null)
    }
  }

  const filtered = Boolean(search || subjectId || year || examType)
  const total = items?.length ?? 0

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Previous Year Questions"
        title="Question Papers"
        description="Published question papers for your enrolled subjects, with secure previews and downloads."
        meta={
          items && total > 0 ? (
            <span className="paper-count">
              {total} published paper{total === 1 ? '' : 's'}
            </span>
          ) : undefined
        }
      />

      <form className="filter-bar" onSubmit={submitSearch}>
        <label>
          Search
          <input
            type="search"
            placeholder="Subject or paper title"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </label>
        <label>
          Subject
          <select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
            <option value="">All enrolled subjects</option>
            {subjects.map((subject) => (
              <option key={subject.id} value={subject.id}>
                {subject.code} — {subject.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Year
          <select value={year} onChange={(event) => setYear(event.target.value)}>
            <option value="">All years</option>
            {YEARS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Exam type
          <select value={examType} onChange={(event) => setExamType(event.target.value)}>
            <option value="">All exams</option>
            <option value="CIE">CIE</option>
            <option value="SEE">SEE</option>
          </select>
        </label>
        <button className="primary-button compact-button" type="submit">Search</button>
        <button className="secondary-button compact-button" type="button" onClick={clearFilters}>
          Clear filters
        </button>
      </form>

      {error && <ErrorState message={error} onRetry={load} />}
      {!items && !error && <LoadingState label="Loading question papers" />}
      {items && (total ? (
        <div className="paper-list">
          {items.map((paper) => {
            const title = paper.title || paper.original_filename
            return (
              <article className="paper-card" key={paper.id}>
                <div className="paper-main">
                  <span className="paper-icon">
                    <PaperIcon />
                  </span>
                  <div className="paper-heading">
                    <strong className="paper-title">{title}</strong>
                    <span className="paper-subtitle">
                      {paper.subject_code} — {paper.subject_name}
                    </span>
                    <div className="paper-meta">
                      <span className="paper-meta-item">
                        <span>Exam</span>
                        {paper.exam_type}
                        {paper.cie_number ? ` ${paper.cie_number}` : ''}
                      </span>
                      <span className="paper-meta-item">
                        <span>Year</span>
                        {paper.examination_year ?? 'Not set'}
                      </span>
                      <span className="paper-meta-item">
                        <span>Code</span>
                        {paper.subject_code}
                      </span>
                      <span className="tag tag-published">Published</span>
                    </div>
                  </div>
                </div>
                <div className="paper-card-actions">
                  <ContentActions
                    withLabels
                    label={title}
                    busy={busy?.id === paper.id}
                    onView={() => void view(paper)}
                    onDownload={() => void download(paper)}
                  />
                </div>
              </article>
            )
          })}
        </div>
      ) : (
        <EmptyState
          title="No question papers found"
          description={
            filtered
              ? 'No published question papers match the current filters. Draft and archived papers are not shown.'
              : 'Previous year question papers for your subjects have not been published yet.'
          }
        />
      ))}
    </section>
  )
}
