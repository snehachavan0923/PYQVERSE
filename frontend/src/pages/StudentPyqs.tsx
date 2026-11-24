import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import { listStudentPyqs, openStudentDownload } from '../services/contentApi'
import notifications from '../services/notification'
import type { QuestionPaperItem } from '../types/dashboard'
import { useStudentSubjects } from '../hooks/useStudentSubjects'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

const CURRENT_YEAR = new Date().getFullYear()
const YEARS = Array.from({ length: 11 }).map((_, index) => CURRENT_YEAR - index)

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
  const [downloading, setDownloading] = useState('')

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

  const download = async (paper: QuestionPaperItem) => {
    setDownloading(paper.id)
    try {
      const url = await openStudentDownload(session, 'pyq', paper.id)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The question paper could not be opened'))
    } finally {
      setDownloading('')
    }
  }

  const filtered = Boolean(search || subjectId || year || examType)

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Previous Year Questions"
        title="Question papers"
        description="Published question papers for your enrolled subjects with secure downloads."
      />
      <form className="filter-bar" onSubmit={submitSearch}>
        <label>
          Search
          <input type="search" placeholder="Subject or paper title" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} />
        </label>
        <label>
          Subject
          <select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
            <option value="">All enrolled subjects</option>
            {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.code} — {subject.name}</option>)}
          </select>
        </label>
        <label>
          Year
          <select value={year} onChange={(event) => setYear(event.target.value)}>
            <option value="">All years</option>
            {YEARS.map((value) => <option key={value} value={value}>{value}</option>)}
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
        <button className="primary-button" type="submit">Search</button>
      </form>
      {error && <ErrorState message={error} onRetry={load} />}
      {!items && !error && <LoadingState label="Loading question papers" />}
      {items && (items.length ? (
        <div className="content-list">
          {items.map((paper) => (
            <article className="content-item" key={paper.id}>
              <div className="content-item-main">
                <strong>{paper.title || paper.original_filename}</strong>
                <p>{paper.subject_code} — {paper.subject_name}</p>
                <div className="content-meta">
                  <span>{paper.exam_type}</span>
                  {paper.cie_number && <span>CIE {paper.cie_number}</span>}
                  <span>{paper.examination_year ?? 'Year not set'}</span>
                  <span className="tag tag-published">Published</span>
                </div>
              </div>
              <div className="content-item-side">
                <button className="primary-button compact-button" type="button" disabled={downloading === paper.id} onClick={() => void download(paper)}>
                  {downloading === paper.id ? 'Opening…' : 'Download'}
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState title="No question papers found" description={filtered ? 'No published question papers match the current filters.' : 'Previous year question papers for your subjects have not been published yet.'} />
      ))}
    </section>
  )
}
