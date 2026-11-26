import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import {
  archiveAdminContent,
  listAdminContent,
  openAdminDownload,
  openAdminPreview,
  updateAdminContent,
  uploadAdminContent,
  type ContentKind,
} from '../services/contentApi'
import notifications from '../services/notification'
import { useAdminSubjects } from '../hooks/useAdminSubjects'
import type {
  LearningResourceItem,
  QuestionPaperItem,
  SyllabusDocumentItem,
} from '../types/dashboard'
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

type ContentItem = SyllabusDocumentItem | QuestionPaperItem | LearningResourceItem

interface AdminContentManagerProps {
  kind: ContentKind
}

const MAX_FILE_BYTES = 20 * 1024 * 1024
const CURRENT_YEAR = new Date().getFullYear()

const STATUS_OPTIONS = [
  { value: 'DRAFT', label: 'Draft' },
  { value: 'PENDING', label: 'Pending review' },
  { value: 'VERIFIED', label: 'Published' },
  { value: 'REJECTED', label: 'Rejected' },
] as const

const RESOURCE_TYPES = [
  { value: 'NOTES', label: 'Notes' },
  { value: 'STUDY_MATERIAL', label: 'Study material' },
  { value: 'REFERENCE', label: 'Reference documents' },
  { value: 'IMPORTANT_QUESTIONS', label: 'Important questions' },
  { value: 'OTHER', label: 'Other' },
] as const

const PAGE_COPY: Record<ContentKind, { eyebrow: string; title: string; description: string }> = {
  syllabus: {
    eyebrow: 'Syllabus management',
    title: 'Syllabus documents',
    description: 'Upload syllabus files, set their publication status, edit metadata and archive superseded versions.',
  },
  pyq: {
    eyebrow: 'PYQ management',
    title: 'Previous year question papers',
    description: 'Upload question papers linked to the academic catalog and control student visibility.',
  },
  resource: {
    eyebrow: 'Learning resources',
    title: 'Learning resources',
    description: 'Publish notes, study material and reference documents for the enrolled academic subjects.',
  },
}

const ACCEPT: Record<ContentKind, string> = {
  syllabus: '.pdf,.docx',
  pyq: '.pdf',
  resource: '.pdf,.docx',
}

function stateTags(status: string, active: boolean) {
  if (!active) {
    return (
      <>
        <span className="tag tag-archived">Archived</span>
        <span className="state-detail">
          Publication: {status === 'VERIFIED' ? 'Published' : status}
        </span>
      </>
    )
  }
  if (status === 'VERIFIED') return <span className="tag tag-published">Published</span>
  if (status === 'REJECTED') return <span className="tag tag-danger">Rejected</span>
  return <span className="tag tag-draft">{status}</span>
}

function titleOf(item: ContentItem) {
  return item.title || item.original_filename
}

function isPyq(item: ContentItem): item is QuestionPaperItem {
  return 'exam_type' in item
}

function isResource(item: ContentItem): item is LearningResourceItem {
  return 'resource_type' in item
}

export default function AdminContentManager({ kind }: AdminContentManagerProps) {
  const { session } = useAuth()
  const subjects = useAdminSubjects()
  const copy = PAGE_COPY[kind]

  const [items, setItems] = useState<ContentItem[] | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [busy, setBusy] = useState<{ id: string; action: 'view' | 'download' } | null>(null)
  const [editing, setEditing] = useState<ContentItem | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [filterSubjectId, setFilterSubjectId] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterArchive, setFilterArchive] = useState('')

  const activeSubjects = useMemo(() => subjects.filter((item) => item.active), [subjects])

  const [uploadForm, setUploadForm] = useState({
    subject_id: '',
    status: 'DRAFT',
    file: null as File | null,
    version: '',
    title: '',
    description: '',
    exam_type: 'SEE',
    examination_year: String(CURRENT_YEAR),
    cie_number: '',
    resource_type: 'NOTES',
  })
  const [editForm, setEditForm] = useState({
    title: '',
    description: '',
    status: 'DRAFT',
    resource_type: 'NOTES',
  })

  const load = useCallback(() => {
    setError('')
    setItems(null)
    listAdminContent<ContentItem>(session, kind)
      .then((data) => setItems(data.items))
      .catch((err) => setError(errorDetail(err, 'Unable to load content')))
  }, [session, kind])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!uploadForm.subject_id && activeSubjects[0]) {
      setUploadForm((current) => ({ ...current, subject_id: activeSubjects[0].id }))
    }
  }, [activeSubjects, uploadForm.subject_id])

  const run = async (action: () => Promise<unknown>, successMessage: string) => {
    if (savingRef.current) return false
    savingRef.current = true
    setSaving(true)
    try {
      await action()
      void notifications.toast('success', successMessage)
      load()
      return true
    } catch (err) {
      void notifications.error('Action not completed', errorDetail(err, 'The request could not be completed'))
      return false
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const submitUpload = async (event: FormEvent) => {
    event.preventDefault()
    if (saving) return
    const file = uploadForm.file
    if (!file) {
      void notifications.error('File required', 'Select a file to upload.')
      return
    }
    if (file.size > MAX_FILE_BYTES) {
      void notifications.error('File too large', 'The maximum file size is 20 MB.')
      return
    }
    const subject = activeSubjects.find((item) => item.id === uploadForm.subject_id)
    if (!subject) {
      void notifications.error('Subject required', 'Select a valid active subject.')
      return
    }
    if (kind === 'resource' && !uploadForm.title.trim()) {
      void notifications.error('Title required', 'Add a title for the learning resource.')
      return
    }

    const ok = await run(
      () =>
        uploadAdminContent(session, kind, {
          subject_id: uploadForm.subject_id,
          status: uploadForm.status,
          file,
          version: kind === 'syllabus' ? uploadForm.version.trim() : undefined,
          title: uploadForm.title.trim() || undefined,
          description: uploadForm.description.trim() || undefined,
          exam_type: kind === 'pyq' ? uploadForm.exam_type : undefined,
          examination_year:
            kind === 'pyq' ? Number(uploadForm.examination_year) : undefined,
          cie_number:
            kind === 'pyq' && uploadForm.exam_type === 'CIE' && uploadForm.cie_number
              ? Number(uploadForm.cie_number)
              : undefined,
          resource_type: kind === 'resource' ? uploadForm.resource_type : undefined,
        }),
      'Content uploaded',
    )
    if (ok) {
      setUploadForm((current) => ({
        ...current,
        file: null,
        version: '',
        title: '',
        description: '',
        examination_year: String(CURRENT_YEAR),
        cie_number: '',
      }))
    }
  }

  const startEdit = (item: ContentItem) => {
    setEditing(item)
    setEditForm({
      title: titleOf(item),
      description: item.description ?? '',
      status: item.verification_status,
      resource_type: isResource(item) ? item.resource_type : 'NOTES',
    })
  }

  const submitEdit = async (event: FormEvent) => {
    event.preventDefault()
    if (!editing || saving) return
    const archived = editing.active === false
    const statusChanged = editForm.status !== editing.verification_status
    const body: Record<string, unknown> = {
      title: editForm.title.trim(),
      description: editForm.description.trim() || null,
      status: editForm.status,
    }
    if (kind === 'resource') body.resource_type = editForm.resource_type
    if (archived && statusChanged) {
      const restore = await notifications.confirm({
        title: 'Restore this archived item?',
        text: 'Changing the publication status of an archived item. Restore it to make it active, or keep it archived.',
        confirmText: 'Restore and save',
        cancelText: 'Keep archived',
      })
      body.active = restore
    }
    const ok = await run(
      () => updateAdminContent(session, kind, editing.id, body),
      'Content updated',
    )
    if (ok) setEditing(null)
  }

  const publish = async (item: ContentItem) => {
    const confirmed = await notifications.confirm({
      title: 'Publish this item?',
      text: 'Published content becomes available to students enrolled in the subject and reactivates archived items.',
      confirmText: 'Publish',
    })
    if (!confirmed) return
    await run(
      () => updateAdminContent(session, kind, item.id, { status: 'VERIFIED', active: true }),
      'Content published',
    )
  }

  const toggleActive = async (item: ContentItem) => {
    const active = item.active !== false
    const confirmed = await notifications.confirm({
      title: active ? 'Archive this item?' : 'Restore this item?',
      text: active
        ? 'Archived items stay stored but are hidden from students.'
        : 'Restored items become visible again according to their publication status.',
      confirmText: active ? 'Archive' : 'Restore',
      destructive: active,
    })
    if (!confirmed) return
    if (active) {
      await run(() => archiveAdminContent(session, kind, item.id), 'Content archived')
    } else {
      await run(() => updateAdminContent(session, kind, item.id, { active: true }), 'Content restored')
    }
  }

  const view = async (item: ContentItem) => {
    const win = openPreviewWindow()
    setBusy({ id: item.id, action: 'view' })
    try {
      const url = await openAdminPreview(session, kind, item.id)
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
      if (retry) void view(item)
      return
    }
    setBusy(null)
  }

  const download = async (item: ContentItem) => {
    setBusy({ id: item.id, action: 'download' })
    try {
      const url = await openAdminDownload(session, kind, item.id)
      triggerDownload(url)
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The file could not be downloaded'))
    } finally {
      setBusy(null)
    }
  }

  const filtered = useMemo(() => {
    if (!items) return []
    const needle = search.trim().toLowerCase()
    return items.filter((item) => {
      if (filterSubjectId && item.subject_id !== filterSubjectId) return false
      if (filterStatus && item.verification_status !== filterStatus) return false
      if (filterArchive === 'active' && item.active === false) return false
      if (filterArchive === 'archived' && item.active !== false) return false
      if (
        needle &&
        !`${titleOf(item)} ${item.original_filename} ${item.subject_code ?? ''} ${item.subject_name ?? ''}`
          .toLowerCase()
          .includes(needle)
      ) {
        return false
      }
      return true
    })
  }, [items, search, filterSubjectId, filterStatus, filterArchive])

  const clearFilters = () => {
    setSearchInput('')
    setSearch('')
    setFilterSubjectId('')
    setFilterStatus('')
    setFilterArchive('')
  }

  return (
    <section className="dashboard-page">
      <PageHeader eyebrow={copy.eyebrow} title={copy.title} description={copy.description} />

      <form
        className="filter-bar"
        onSubmit={(event) => {
          event.preventDefault()
          setSearch(searchInput.trim())
        }}
      >
        <label>
          Search
          <input
            type="search"
            placeholder="Title or filename"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </label>
        <label>
          Subject
          <select value={filterSubjectId} onChange={(event) => setFilterSubjectId(event.target.value)}>
            <option value="">All subjects</option>
            {subjects.map((subject) => (
              <option key={subject.id} value={subject.id}>
                {subject.code} — {subject.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Publication status
          <select value={filterStatus} onChange={(event) => setFilterStatus(event.target.value)}>
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label>
          Archive state
          <select value={filterArchive} onChange={(event) => setFilterArchive(event.target.value)}>
            <option value="">All states</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <button className="primary-button compact-button" type="submit">Search</button>
        <button className="secondary-button compact-button" type="button" onClick={clearFilters}>
          Clear filters
        </button>
      </form>

      <div className="two-column-grid">
        <form className="editor-panel" onSubmit={submitUpload}>
          <h2>Upload {kind === 'pyq' ? 'question paper' : kind === 'syllabus' ? 'syllabus' : 'resource'}</h2>
          <label>
            Subject
            <select
              value={uploadForm.subject_id}
              onChange={(event) => setUploadForm({ ...uploadForm, subject_id: event.target.value })}
              required
            >
              <option value="">Select subject</option>
              {activeSubjects.map((subject) => (
                <option key={subject.id} value={subject.id}>
                  {subject.code} — {subject.name}
                </option>
              ))}
            </select>
          </label>
          {kind === 'syllabus' && (
            <label>
              Version
              <input
                value={uploadForm.version}
                onChange={(event) => setUploadForm({ ...uploadForm, version: event.target.value })}
                placeholder="e.g. 2025-v1"
                required
                maxLength={50}
              />
            </label>
          )}
          {kind === 'pyq' && (
            <div className="editor-grid">
              <label>
                Exam type
                <select
                  value={uploadForm.exam_type}
                  onChange={(event) => setUploadForm({ ...uploadForm, exam_type: event.target.value })}
                >
                  <option value="CIE">CIE</option>
                  <option value="SEE">SEE</option>
                </select>
              </label>
              <label>
                Examination year
                <input
                  type="number"
                  min={2000}
                  max={2100}
                  value={uploadForm.examination_year}
                  onChange={(event) => setUploadForm({ ...uploadForm, examination_year: event.target.value })}
                  required
                />
              </label>
              {uploadForm.exam_type === 'CIE' && (
                <label>
                  CIE number (optional)
                  <input
                    type="number"
                    min={1}
                    max={3}
                    value={uploadForm.cie_number}
                    onChange={(event) => setUploadForm({ ...uploadForm, cie_number: event.target.value })}
                  />
                </label>
              )}
            </div>
          )}
          {kind === 'resource' && (
            <label>
              Resource type
              <select
                value={uploadForm.resource_type}
                onChange={(event) => setUploadForm({ ...uploadForm, resource_type: event.target.value })}
              >
                {RESOURCE_TYPES.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </label>
          )}
          <label>
            Title (optional)
            <input
              value={uploadForm.title}
              onChange={(event) => setUploadForm({ ...uploadForm, title: event.target.value })}
              maxLength={300}
            />
          </label>
          <label>
            Description (optional)
            <textarea
              rows={3}
              value={uploadForm.description}
              onChange={(event) => setUploadForm({ ...uploadForm, description: event.target.value })}
              maxLength={4000}
            />
          </label>
          <label>
            File
            <input
              type="file"
              accept={ACCEPT[kind]}
              onChange={(event) => setUploadForm({ ...uploadForm, file: event.target.files?.[0] ?? null })}
              required
            />
          </label>
          <label>
            Publication status
            <select
              value={uploadForm.status}
              onChange={(event) => setUploadForm({ ...uploadForm, status: event.target.value })}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <p className="form-hint">Accepted files: PDF{kind === 'pyq' ? '' : ' or DOCX'}. Maximum size: 20 MB.</p>
          <div className="form-actions">
            <button className="primary-button compact-button" disabled={saving || !activeSubjects.length}>
              {saving ? 'Uploading…' : 'Upload'}
            </button>
          </div>
        </form>

        {editing ? (
          <form className="editor-panel" onSubmit={submitEdit}>
            <div className="section-heading">
              <h2>Edit metadata</h2>
              <button className="secondary-button compact-button" type="button" onClick={() => setEditing(null)}>
                Cancel
              </button>
            </div>
            <label>
              Title
              <input
                value={editForm.title}
                onChange={(event) => setEditForm({ ...editForm, title: event.target.value })}
                required
                maxLength={300}
              />
            </label>
            <label>
              Description
              <textarea
                rows={3}
                value={editForm.description}
                onChange={(event) => setEditForm({ ...editForm, description: event.target.value })}
                maxLength={4000}
              />
            </label>
            {kind === 'resource' && (
              <label>
                Resource type
                <select
                  value={editForm.resource_type}
                  onChange={(event) => setEditForm({ ...editForm, resource_type: event.target.value })}
                >
                  {RESOURCE_TYPES.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Publication status
              <select
                value={editForm.status}
                onChange={(event) => setEditForm({ ...editForm, status: event.target.value })}
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <div className="form-actions">
              <button className="primary-button compact-button" disabled={saving}>
                {saving ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          </form>
        ) : (
          <article className="editor-panel">
            <h2>Manage {kind === 'pyq' ? 'question papers' : kind === 'syllabus' ? 'syllabus documents' : 'resources'}</h2>
            <p className="muted">
              Use the filters above to find content. Archived items remain stored and can be restored;
              only published active items are visible to students.
            </p>
            <p className="metric-note">Showing {filtered.length} of {items?.length ?? 0} items</p>
          </article>
        )}
      </div>

      {error && <ErrorState message={error} onRetry={load} />}
      {!items && !error && <LoadingState label="Loading content" rows={3} />}
      {items && (filtered.length ? (
        <div className="content-list">
          {filtered.map((item) => {
            const active = item.active !== false
            return (
              <article className="content-item" key={item.id}>
                <div className="content-item-main">
                  <strong>{titleOf(item)}</strong>
                  <p>
                    {item.subject_code ?? 'Subject removed'} — {item.subject_name ?? 'Unknown subject'}
                    {isPyq(item)
                      ? ` · ${item.exam_type}${item.cie_number ? ` ${item.cie_number}` : ''} · ${item.examination_year ?? 'Year not set'}`
                      : ''}
                    {isResource(item) ? ` · ${item.resource_type.replaceAll('_', ' ')}` : ''}
                    {!isPyq(item) && !isResource(item) && item.version ? ` · Version ${item.version}` : ''}
                  </p>
                  <div className="content-meta">
                    {stateTags(item.verification_status, active)}
                    <span>{item.file_type.toUpperCase()}</span>
                    <span>{item.original_filename}</span>
                  </div>
                </div>
                <div className="content-item-side">
                  <div className="row-actions">
                    {item.verification_status === 'VERIFIED' ? null : (
                      <button
                        className="primary-button compact-button"
                        type="button"
                        disabled={saving}
                        onClick={() => void publish(item)}
                      >
                        Publish
                      </button>
                    )}
                    <button className="secondary-button compact-button" type="button" onClick={() => startEdit(item)}>
                      Edit
                    </button>
                    <ContentActions
                      label={titleOf(item)}
                      busy={busy?.id === item.id}
                      viewDisabled={!isPdfFile(item.file_type)}
                      viewHint={isPdfFile(item.file_type) ? 'View PDF in a new tab' : 'Preview is available for PDF documents only'}
                      onView={() => void view(item)}
                      onDownload={() => void download(item)}
                    />
                    <button
                      className={active ? 'danger-button compact-button' : 'secondary-button compact-button'}
                      type="button"
                      disabled={saving}
                      onClick={() => void toggleActive(item)}
                    >
                      {active ? 'Archive' : 'Restore'}
                    </button>
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      ) : (
        <EmptyState
          title="No content found"
          description={
            items.length
              ? 'No uploaded items match the current search and filters.'
              : 'Use the upload form to add the first document.'
          }
        />
      ))}
    </section>
  )
}
