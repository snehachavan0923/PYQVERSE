import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import {
  archiveAdminContent,
  deleteAdminContent,
  listAdminContent,
  listAdminUnits,
  openAdminDownload,
  openAdminPreview,
  updateAdminContent,
  uploadAdminContent,
  type AdminUnitItem,
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
import Modal from '../components/Modal'
import { LoadingState, ErrorState } from '../components/PageState'
import {
  closePreviewWindow,
  isPdfFile,
  loadPreview,
  openPreviewWindow,
  triggerDownload,
} from '../utils/documentActions'
import {
  detectResourceSource,
  getDomain,
  isValidHttpUrl,
  parseYouTubeUrl,
} from '../utils/resourceUtils'

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
    description: 'Publish notes, study material, video links and reference documents for the enrolled academic subjects.',
  },
}

const ACCEPT: Record<ContentKind, string> = {
  syllabus: '.pdf,.docx',
  pyq: '.pdf',
  resource: '.pdf,.docx',
}

const UPLOAD_FORM_ID = 'admin-upload-document-form'

const UPLOAD_COPY: Record<ContentKind, { title: string; description: string; manage: string }> = {
  syllabus: {
    title: 'Upload Syllabus Document',
    description: 'Add a syllabus version to an active subject and choose when students can access it.',
    manage: 'syllabus documents',
  },
  pyq: {
    title: 'Upload Question Paper',
    description: 'Add a question paper to the academic catalog and control its student visibility.',
    manage: 'question papers',
  },
  resource: {
    title: 'Upload Learning Resource',
    description: 'Add notes, study material, or external links for an active subject and control student access.',
    manage: 'learning resources',
  },
}

interface UploadFormState {
  subject_id: string
  status: string
  file: File | null
  resource_source: 'FILE' | 'LINK' | 'BOTH'
  external_url: string
  link_title: string
  unit_id: string
  version: string
  title: string
  description: string
  exam_type: string
  examination_year: string
  cie_number: string
  resource_type: string
}

function emptyUploadForm(): UploadFormState {
  return {
    subject_id: '',
    status: 'DRAFT',
    file: null,
    resource_source: 'FILE',
    external_url: '',
    link_title: '',
    unit_id: '',
    version: '',
    title: '',
    description: '',
    exam_type: 'SEE',
    examination_year: String(CURRENT_YEAR),
    cie_number: '',
    resource_type: 'NOTES',
  }
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6h18" />
      <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
      <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
      <line x1="10" x2="10" y1="11" y2="17" />
      <line x1="14" x2="14" y1="11" y2="17" />
    </svg>
  )
}

function contentTypeLabel(kind: ContentKind): string {
  switch (kind) {
    case 'pyq':
      return 'Previous Year Question Paper (PYQ)'
    case 'syllabus':
      return 'Syllabus Document'
    case 'resource':
      return 'Learning Resource'
  }
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

function titleOf(item: ContentItem): string {
  return item.title || item.original_filename || 'Untitled document'
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
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const uploadErrorRef = useRef<HTMLParagraphElement>(null)
  const [busy, setBusy] = useState<{ id: string; action: 'view' | 'download' } | null>(null)
  const [editing, setEditing] = useState<ContentItem | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [filterSubjectId, setFilterSubjectId] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterArchive, setFilterArchive] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<ContentItem | null>(null)
  const [deleting, setDeleting] = useState(false)

  const activeSubjects = useMemo(() => subjects.filter((item) => item.active), [subjects])

  const [uploadForm, setUploadForm] = useState<UploadFormState>(emptyUploadForm)
  const [units, setUnits] = useState<AdminUnitItem[]>([])
  const [editForm, setEditForm] = useState({
    title: '',
    description: '',
    status: 'DRAFT',
    resource_type: 'NOTES',
    subject_id: '',
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
      setUploadForm((current) => ({ ...current, subject_id: filterSubjectId || activeSubjects[0].id }))
    }
  }, [activeSubjects, filterSubjectId, uploadForm.subject_id])

  useEffect(() => {
    if (kind === 'resource' && uploadForm.subject_id) {
      listAdminUnits(session, uploadForm.subject_id)
        .then(setUnits)
        .catch(() => setUnits([]))
    } else {
      setUnits([])
    }
  }, [kind, session, uploadForm.subject_id])

  useEffect(() => {
    if (uploadError) uploadErrorRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [uploadError])

  const updateUploadForm = (patch: Partial<UploadFormState>) => {
    setUploadForm((current) => ({ ...current, ...patch }))
    setUploadError('')
  }

  const resetUploadForm = () => {
    setUploadForm({
      ...emptyUploadForm(),
      subject_id: filterSubjectId || '',
    })
    setUploadError('')
  }

  const openUpload = () => {
    setUploadError('')
    setUploadForm((current) => ({
      ...current,
      subject_id: filterSubjectId || current.subject_id || '',
    }))
    setUploadOpen(true)
  }

  const closeUpload = () => {
    if (savingRef.current) return
    setUploadOpen(false)
    resetUploadForm()
  }

  const run = async (
    action: () => Promise<unknown>,
    successMessage: string,
    options?: { inlineError?: boolean },
  ) => {
    if (savingRef.current) return false
    savingRef.current = true
    setSaving(true)
    try {
      await action()
      void notifications.toast('success', successMessage)
      load()
      return true
    } catch (err) {
      const detail = errorDetail(err, 'The request could not be completed')
      if (options?.inlineError) setUploadError(detail)
      else void notifications.error('Action not completed', detail)
      return false
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const submitUpload = async (event: FormEvent) => {
    event.preventDefault()
    if (savingRef.current) return

    const subject = activeSubjects.find((item) => item.id === uploadForm.subject_id)
    if (!subject) {
      setUploadError('Select a valid active subject.')
      return
    }

    const file = uploadForm.file
    const source = uploadForm.resource_source

    if (kind === 'resource') {
      if (source === 'FILE' || source === 'BOTH') {
        if (!file) {
          setUploadError('Select a file to upload.')
          return
        }
        if (file.size > MAX_FILE_BYTES) {
          setUploadError('The maximum file size is 20 MB.')
          return
        }
      }
      if (source === 'LINK' || source === 'BOTH') {
        const url = uploadForm.external_url.trim()
        if (!url) {
          setUploadError('Enter a valid resource URL.')
          return
        }
        if (!isValidHttpUrl(url)) {
          setUploadError('Please enter a valid HTTP or HTTPS URL (e.g. https://...).')
          return
        }
      }
      if (!uploadForm.title.trim()) {
        setUploadError('Add a title for the learning resource.')
        return
      }
    } else {
      if (!file) {
        setUploadError('Select a file to upload.')
        return
      }
      if (file.size > MAX_FILE_BYTES) {
        setUploadError('The maximum file size is 20 MB.')
        return
      }
    }

    if (kind === 'syllabus' && !uploadForm.version.trim()) {
      setUploadError('Add a syllabus version.')
      return
    }

    if (kind === 'pyq') {
      const year = Number(uploadForm.examination_year)
      if (!Number.isInteger(year) || year < 2000 || year > 2100) {
        setUploadError('Enter an examination year between 2000 and 2100.')
        return
      }
      if (uploadForm.exam_type === 'CIE' && uploadForm.cie_number) {
        const cieNumber = Number(uploadForm.cie_number)
        if (!Number.isInteger(cieNumber) || cieNumber < 1 || cieNumber > 3) {
          setUploadError('CIE number must be between 1 and 3.')
          return
        }
      }
    }

    const ok = await run(
      () =>
        uploadAdminContent(session, kind, {
          subject_id: uploadForm.subject_id,
          status: uploadForm.status,
          file: (kind !== 'resource' || source === 'FILE' || source === 'BOTH') ? file : null,
          resource_source: kind === 'resource' ? uploadForm.resource_source : undefined,
          external_url:
            kind === 'resource' && (source === 'LINK' || source === 'BOTH')
              ? uploadForm.external_url.trim()
              : undefined,
          link_title:
            kind === 'resource' && uploadForm.link_title.trim()
              ? uploadForm.link_title.trim()
              : undefined,
          unit_id:
            kind === 'resource' && uploadForm.unit_id
              ? uploadForm.unit_id
              : undefined,
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
      { inlineError: true },
    )
    if (ok) {
      setUploadOpen(false)
      resetUploadForm()
    }
  }

  const startEdit = (item: ContentItem) => {
    setEditing(item)
    setEditForm({
      title: titleOf(item),
      description: item.description ?? '',
      status: item.verification_status,
      resource_type: isResource(item) ? item.resource_type : 'NOTES',
      subject_id: item.subject_id ?? '',
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
    if (editForm.subject_id && editForm.subject_id !== editing.subject_id) {
      body.subject_id = editForm.subject_id
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

  const confirmDelete = async () => {
    if (!deleteTarget || deleting) return
    setDeleting(true)
    try {
      await deleteAdminContent(session, kind, deleteTarget.id)
      setItems((prev) => (prev ? prev.filter((i) => i.id !== deleteTarget.id) : null))
      setDeleteTarget(null)
      void notifications.toast('success', 'Content deleted successfully')
    } catch (err) {
      void notifications.error('Deletion failed', errorDetail(err, 'Failed to delete the selected content'))
    } finally {
      setDeleting(false)
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
      <PageHeader
        className="content-manager-header"
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.description}
        actions={
          <button className="primary-button compact-button" type="button" onClick={openUpload}>
            <UploadIcon />
            Upload Document
          </button>
        }
      />

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

      {editing ? (
        <form className="editor-panel content-edit-panel" onSubmit={submitEdit}>
            <div className="section-heading">
              <h2>Edit metadata</h2>
              <button className="secondary-button compact-button" type="button" onClick={() => setEditing(null)}>
                Cancel
              </button>
            </div>
            <label>
              Subject
              <select
                value={editForm.subject_id}
                onChange={(event) => setEditForm({ ...editForm, subject_id: event.target.value })}
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
      ) : null}

      <div className="content-summary">
        <div>
          <h2>Manage {UPLOAD_COPY[kind].manage}</h2>
          <p className="muted">
            Use the filters above to find content. Archived items remain stored and can be restored;
            only published active items are visible to students.
          </p>
        </div>
        <span className="metric-note">Showing {filtered.length} of {items?.length ?? 0} items</span>
      </div>

      <Modal
        open={uploadOpen}
        title={UPLOAD_COPY[kind].title}
        description={UPLOAD_COPY[kind].description}
        busy={saving}
        onClose={closeUpload}
        footer={
          <>
            <button className="secondary-button compact-button" type="button" disabled={saving} onClick={closeUpload}>
              Cancel
            </button>
            <button
              className="primary-button compact-button"
              type="submit"
              form={UPLOAD_FORM_ID}
              disabled={saving || !activeSubjects.length}
            >
              {saving ? 'Uploading…' : 'Upload'}
            </button>
          </>
        }
      >
        <form id={UPLOAD_FORM_ID} className="upload-modal-form" onSubmit={submitUpload} noValidate>
          {uploadError && <p className="form-error" role="alert" ref={uploadErrorRef}>{uploadError}</p>}
          <label>
            Subject
            <select
              data-autofocus
              value={uploadForm.subject_id}
              onChange={(event) => updateUploadForm({ subject_id: event.target.value })}
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
                onChange={(event) => updateUploadForm({ version: event.target.value })}
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
                  onChange={(event) => updateUploadForm({ exam_type: event.target.value })}
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
                  onChange={(event) => updateUploadForm({ examination_year: event.target.value })}
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
                    onChange={(event) => updateUploadForm({ cie_number: event.target.value })}
                  />
                </label>
              )}
            </div>
          )}
          {kind === 'resource' && (
            <div className="source-selector-container">
              <label className="field-label" style={{ marginBottom: '6px', display: 'block', fontWeight: 500 }}>
                Resource Source
              </label>
              <div className="source-selector" role="radiogroup" aria-label="Resource Source">
                <button
                  type="button"
                  role="radio"
                  aria-label="File Upload"
                  aria-checked={uploadForm.resource_source === 'FILE'}
                  className={`source-card${uploadForm.resource_source === 'FILE' ? ' active' : ''}`}
                  onClick={() => updateUploadForm({ resource_source: 'FILE' })}
                >
                  <div className="source-card-title">
                    <span>📄</span>
                    <span>File Upload</span>
                  </div>
                  <span className="source-card-desc">PDF or DOCX document (up to 20 MB)</span>
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-label="External Link"
                  aria-checked={uploadForm.resource_source === 'LINK'}
                  className={`source-card${uploadForm.resource_source === 'LINK' ? ' active' : ''}`}
                  onClick={() => updateUploadForm({ resource_source: 'LINK' })}
                >
                  <div className="source-card-title">
                    <span>🔗</span>
                    <span>External Link</span>
                  </div>
                  <span className="source-card-desc">YouTube video, playlist or website</span>
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-label="Both"
                  aria-checked={uploadForm.resource_source === 'BOTH'}
                  className={`source-card${uploadForm.resource_source === 'BOTH' ? ' active' : ''}`}
                  onClick={() => updateUploadForm({ resource_source: 'BOTH' })}
                >
                  <div className="source-card-title">
                    <span>📄+🔗</span>
                    <span>Both</span>
                  </div>
                  <span className="source-card-desc">Document with attached external link</span>
                </button>
              </div>
            </div>
          )}
          {kind === 'resource' && (
            <label>
              Resource type
              <select
                value={uploadForm.resource_type}
                onChange={(event) => updateUploadForm({ resource_type: event.target.value })}
              >
                {RESOURCE_TYPES.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </label>
          )}
          {kind === 'resource' && units.length > 0 && (
            <label>
              Unit / Topic (optional)
              <select
                value={uploadForm.unit_id}
                onChange={(event) => updateUploadForm({ unit_id: event.target.value })}
              >
                <option value="">Select unit (optional)</option>
                {units.map((u) => (
                  <option key={u.id} value={u.id}>
                    Unit {u.order_index}: {u.title}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Title {kind === 'resource' ? '(required)' : '(optional)'}
            <input
              value={uploadForm.title}
              onChange={(event) => updateUploadForm({ title: event.target.value })}
              maxLength={300}
              required={kind === 'resource'}
            />
          </label>
          <label>
            Description (optional)
            <textarea
              rows={3}
              value={uploadForm.description}
              onChange={(event) => updateUploadForm({ description: event.target.value })}
              maxLength={4000}
            />
          </label>
          {kind === 'resource' && (uploadForm.resource_source === 'LINK' || uploadForm.resource_source === 'BOTH') && (
            <>
              <label>
                Resource URL
                <input
                  type="url"
                  placeholder="https://www.youtube.com/watch?v=... or https://..."
                  value={uploadForm.external_url}
                  onChange={(event) => updateUploadForm({ external_url: event.target.value })}
                  required
                />
              </label>

              {uploadForm.external_url.trim() && (() => {
                const yt = parseYouTubeUrl(uploadForm.external_url)
                const isHttp = isValidHttpUrl(uploadForm.external_url)
                if (yt.isYouTube) {
                  return (
                    <div className="resource-url-preview">
                      {yt.thumbnailUrl && (
                        <div className="resource-yt-thumb">
                          <img src={yt.thumbnailUrl} alt="YouTube thumbnail" />
                          <div className="resource-play-overlay">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                              <polygon points="5 3 19 12 5 21 5 3" />
                            </svg>
                          </div>
                        </div>
                      )}
                      <div className="resource-url-preview-info">
                        <span className="resource-url-badge badge-youtube">
                          {yt.isPlaylist ? '📑 YouTube Playlist' : '▶ YouTube Video'}
                        </span>
                        <span className="mono-text" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                          {yt.videoId ? `Video ID: ${yt.videoId}` : `Playlist ID: ${yt.playlistId}`}
                        </span>
                      </div>
                    </div>
                  )
                }
                if (isHttp) {
                  return (
                    <div className="resource-url-preview">
                      <div className="resource-url-preview-info">
                        <span className="resource-url-badge badge-web">🌐 Educational Website</span>
                        <strong style={{ fontSize: '13px', color: 'var(--text)' }}>{getDomain(uploadForm.external_url)}</strong>
                        <span className="mono-text" style={{ fontSize: '11px', color: 'var(--muted)', overflowWrap: 'anywhere' }}>
                          {uploadForm.external_url}
                        </span>
                      </div>
                    </div>
                  )
                }
                return (
                  <p className="form-hint" style={{ color: 'var(--warning)' }}>
                    Please enter a valid URL beginning with http:// or https://
                  </p>
                )
              })()}

              <label>
                Link title (optional)
                <input
                  value={uploadForm.link_title}
                  onChange={(event) => updateUploadForm({ link_title: event.target.value })}
                  placeholder="e.g. Official Lecture Video / Course Documentation"
                  maxLength={300}
                />
              </label>
            </>
          )}
          {(kind !== 'resource' || uploadForm.resource_source === 'FILE' || uploadForm.resource_source === 'BOTH') && (
            <label>
              File
              <input
                type="file"
                accept={ACCEPT[kind]}
                onChange={(event) => updateUploadForm({ file: event.target.files?.[0] ?? null })}
                required
              />
            </label>
          )}
          <label>
            Publication status
            <select
              value={uploadForm.status}
              onChange={(event) => updateUploadForm({ status: event.target.value })}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <p className="form-hint">
            {kind === 'resource' && uploadForm.resource_source === 'LINK'
              ? 'External link: YouTube video, playlist or educational site URL.'
              : `Accepted files: PDF${kind === 'pyq' ? '' : ' or DOCX'}. Maximum size: 20 MB.`}
          </p>
        </form>
      </Modal>

      <Modal
        open={Boolean(deleteTarget)}
        title="Confirm Permanent Deletion"
        description="This action cannot be undone. Please confirm before proceeding."
        busy={deleting}
        onClose={() => !deleting && setDeleteTarget(null)}
        footer={
          <>
            <button
              className="secondary-button compact-button"
              type="button"
              disabled={deleting}
              onClick={() => setDeleteTarget(null)}
              data-autofocus
            >
              Cancel
            </button>
            <button
              className="danger-button compact-button"
              type="button"
              disabled={deleting}
              onClick={() => void confirmDelete()}
            >
              {deleting ? 'Deleting…' : 'Confirm Delete'}
            </button>
          </>
        }
      >
        {deleteTarget && (
          <div className="delete-modal-content">
            <div className="delete-modal-field">
              <span className="muted">Document name:</span>
              <strong>{titleOf(deleteTarget)}</strong>
            </div>
            <div className="delete-modal-field">
              <span className="muted">Content type:</span>
              <span>{contentTypeLabel(kind)}</span>
            </div>
            <div className="delete-modal-field">
              <span className="muted">Filename / Link:</span>
              <span className="mono-text">{deleteTarget.original_filename || deleteTarget.external_url || 'No file attached'}</span>
            </div>
            <div className="delete-warning-banner" role="alert">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <p>
                <strong>Warning:</strong> Deleting this content removes its stored file and database record permanently. This may affect student access to enrolled academic materials for this subject.
              </p>
            </div>
          </div>
        )}
      </Modal>

      {error && <ErrorState message={error} onRetry={load} />}
      {!items && !error && <LoadingState label="Loading content" rows={3} />}
      {items && (filtered.length ? (
        <div className="content-list">
          {filtered.map((item) => {
            const active = item.active !== false
            const isRes = isResource(item)
            const source = isRes ? detectResourceSource(item) : 'FILE'
            const hasFile = isRes
              ? (source === 'FILE' || source === 'BOTH' || Boolean(item.file_size))
              : true
            const yt = isRes && item.external_url ? parseYouTubeUrl(item.external_url) : null

            return (
              <article className="content-item" key={item.id}>
                <div className="content-item-main">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <strong>{titleOf(item)}</strong>
                    {isRes && (
                      <span className={`tag tag-source-${source.toLowerCase()}`}>
                        {source === 'FILE' ? '📄 File' : source === 'LINK' ? '🔗 Link' : '📄+🔗 File & Link'}
                      </span>
                    )}
                  </div>
                  <p>
                    {item.subject_code ?? 'Subject removed'} — {item.subject_name ?? 'Unknown subject'}
                    {isPyq(item)
                      ? ` · ${item.exam_type}${item.cie_number ? ` ${item.cie_number}` : ''} · ${item.examination_year ?? 'Year not set'}`
                      : ''}
                    {isRes ? ` · ${item.resource_type.replaceAll('_', ' ')}` : ''}
                    {isRes && item.unit_title ? ` · Unit ${item.unit_number ?? ''}: ${item.unit_title}` : ''}
                    {!isPyq(item) && !isRes && item.version ? ` · Version ${item.version}` : ''}
                  </p>
                  {isRes && item.description && <p style={{ color: 'var(--text-secondary)' }}>{item.description}</p>}
                  {isRes && item.external_url && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', marginTop: '2px' }}>
                      <span style={{ color: 'var(--muted)' }}>URL:</span>
                      <a
                        href={item.external_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--primary)', textDecoration: 'underline', overflowWrap: 'anywhere' }}
                      >
                        {item.link_title || item.external_url}
                      </a>
                    </div>
                  )}
                  <div className="content-meta">
                    {stateTags(item.verification_status, active)}
                    {hasFile && item.file_type && <span>{item.file_type.toUpperCase()}</span>}
                    {hasFile && item.original_filename && <span>{item.original_filename}</span>}
                    {isRes && !hasFile && <span>External Link Only</span>}
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
                    {isRes && item.external_url && (
                      <a
                        className="secondary-button compact-button resource-link-btn"
                        href={item.external_url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {yt?.isYouTube ? '▶ Watch Video' : '↗ Open Link'}
                      </a>
                    )}
                    {hasFile && (
                      <ContentActions
                        label={titleOf(item)}
                        busy={busy?.id === item.id}
                        viewDisabled={!isPdfFile(item.file_type || '')}
                        viewHint={isPdfFile(item.file_type || '') ? 'View PDF in a new tab' : 'Preview is available for PDF documents only'}
                        onView={() => void view(item)}
                        onDownload={() => void download(item)}
                      />
                    )}
                    <button
                      className={active ? 'danger-button compact-button' : 'secondary-button compact-button'}
                      type="button"
                      disabled={saving}
                      onClick={() => void toggleActive(item)}
                    >
                      {active ? 'Archive' : 'Restore'}
                    </button>
                    <button
                      className="danger-button compact-button delete-action-btn"
                      type="button"
                      aria-label={`Delete ${titleOf(item)}`}
                      disabled={saving || (deleting && deleteTarget?.id === item.id)}
                      onClick={() => setDeleteTarget(item)}
                    >
                      <TrashIcon />
                      <span>Delete</span>
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
              : `Upload your first ${kind === 'pyq' ? 'question paper' : kind === 'syllabus' ? 'syllabus document' : 'learning resource'} to start managing content.`
          }
          action={
            items.length ? undefined : (
              <button className="primary-button compact-button" type="button" onClick={openUpload}>
                <UploadIcon />
                Upload Document
              </button>
            )
          }
        />
      ))}
    </section>
  )
}
