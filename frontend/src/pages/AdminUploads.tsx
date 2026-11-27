import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import { openAdminDownload, openAdminPreview, deleteAdminContent, type ContentKind } from '../services/contentApi'
import notifications from '../services/notification'
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

type UploadKind = 'SYLLABUS' | 'PYQ' | 'RESOURCE'

interface UploadItem {
  kind: UploadKind
  id: string
  title: string
  subject_code: string | null
  status: string
  active: boolean
  created_at: string | null
  size: number | null
  file_type: string | null
}

interface UploadResponse {
  items: UploadItem[]
  total: number
}

const KIND_LABELS: Record<UploadKind, string> = {
  SYLLABUS: 'Syllabus',
  PYQ: 'Question paper',
  RESOURCE: 'Learning resource',
}

function downloadKind(kind: UploadKind): ContentKind {
  if (kind === 'SYLLABUS') return 'syllabus'
  if (kind === 'PYQ') return 'pyq'
  return 'resource'
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function formatSize(value: number | null) {
  if (!value) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
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

export default function AdminUploads() {
  const { session } = useAuth()
  const [data, setData] = useState<UploadResponse | null>(null)
  const [error, setError] = useState('')
  const [kindFilter, setKindFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [archiveFilter, setArchiveFilter] = useState('')
  const [busy, setBusy] = useState<{ id: string; action: 'view' | 'download' } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<UploadItem | null>(null)
  const [deleting, setDeleting] = useState(false)

  const confirmDelete = async () => {
    if (!deleteTarget || deleting) return
    setDeleting(true)
    try {
      await deleteAdminContent(session, downloadKind(deleteTarget.kind), deleteTarget.id)
      setData((prev) => (prev ? { ...prev, items: prev.items.filter((i) => i.id !== deleteTarget.id), total: prev.total - 1 } : null))
      setDeleteTarget(null)
      void notifications.toast('success', 'Upload deleted successfully')
    } catch (err) {
      void notifications.error('Deletion failed', errorDetail(err, 'Failed to delete the selected upload'))
    } finally {
      setDeleting(false)
    }
  }

  const load = useCallback(() => {
    setError('')
    setData(null)
    getWithAuth<UploadResponse>('/admin/uploads', session)
      .then(setData)
      .catch((err) => setError(errorDetail(err, 'Unable to load uploads')))
  }, [session])

  useEffect(() => {
    load()
  }, [load])

  const visible = useMemo(() => {
    if (!data) return []
    return data.items.filter((item) => {
      if (kindFilter && item.kind !== kindFilter) return false
      if (statusFilter && item.status !== statusFilter) return false
      if (archiveFilter === 'active' && !item.active) return false
      if (archiveFilter === 'archived' && item.active) return false
      return true
    })
  }, [data, kindFilter, statusFilter, archiveFilter])

  const clearFilters = () => {
    setKindFilter('')
    setStatusFilter('')
    setArchiveFilter('')
  }

  const view = async (item: UploadItem) => {
    const win = openPreviewWindow()
    setBusy({ id: item.id, action: 'view' })
    try {
      const url = await openAdminPreview(session, downloadKind(item.kind), item.id)
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

  const download = async (item: UploadItem) => {
    setBusy({ id: item.id, action: 'download' })
    try {
      const url = await openAdminDownload(session, downloadKind(item.kind), item.id)
      triggerDownload(url)
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The file could not be downloaded'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Uploads"
        title="Uploaded content"
        description="Every syllabus, question paper and learning resource recorded in private storage."
        actions={
          <button className="secondary-button compact-button" type="button" onClick={load}>
            Refresh
          </button>
        }
      />

      <div className="filter-bar">
        <label>
          Content type
          <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}>
            <option value="">All content types</option>
            <option value="SYLLABUS">Syllabus</option>
            <option value="PYQ">Question papers</option>
            <option value="RESOURCE">Learning resources</option>
          </select>
        </label>
        <label>
          Publication status
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">All statuses</option>
            <option value="DRAFT">Draft</option>
            <option value="PENDING">Pending review</option>
            <option value="VERIFIED">Published</option>
            <option value="REJECTED">Rejected</option>
          </select>
        </label>
        <label>
          Archive state
          <select value={archiveFilter} onChange={(event) => setArchiveFilter(event.target.value)}>
            <option value="">All states</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <button className="secondary-button compact-button" type="button" onClick={clearFilters}>
          Clear filters
        </button>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}
      {!data && !error && <LoadingState label="Loading uploads" rows={3} />}
      {data && (visible.length ? (
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Title</th>
                <th>Subject</th>
                <th>Status</th>
                <th>Size</th>
                <th>Uploaded</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={`${item.kind}-${item.id}`}>
                  <td><span className="type-pill">{KIND_LABELS[item.kind]}</span></td>
                  <td><strong>{item.title}</strong></td>
                  <td>{item.subject_code ?? '—'}</td>
                  <td>
                    {item.active ? (
                      item.status === 'VERIFIED' ? 'Published' : item.status
                    ) : (
                      <>
                        <strong>Archived</strong>
                        <span className="table-subtext">
                          Publication: {item.status === 'VERIFIED' ? 'Published' : item.status}
                        </span>
                      </>
                    )}
                  </td>
                  <td>{formatSize(item.size)}</td>
                  <td>{formatDate(item.created_at)}</td>
                  <td>
                    <div className="row-actions">
                      <ContentActions
                        label={item.title}
                        busy={busy?.id === item.id}
                        viewDisabled={!isPdfFile(item.file_type)}
                        viewHint={isPdfFile(item.file_type) ? 'View PDF in a new tab' : 'Preview is available for PDF documents only'}
                        onView={() => void view(item)}
                        onDownload={() => void download(item)}
                      />
                      <button
                        className="danger-button compact-button delete-action-btn"
                        type="button"
                        aria-label={`Delete ${item.title}`}
                        disabled={deleting && deleteTarget?.id === item.id}
                        onClick={() => setDeleteTarget(item)}
                      >
                        <TrashIcon />
                        <span>Delete</span>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pagination-bar">
            <span>{visible.length} of {data.total} uploads</span>
          </div>
        </div>
      ) : (
        <EmptyState
          title="No uploads found"
          description={data.total ? 'No uploads match the current content type filter.' : 'Uploaded documents will appear here.'}
        />
      ))}

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
              <strong>{deleteTarget.title}</strong>
            </div>
            <div className="delete-modal-field">
              <span className="muted">Content type:</span>
              <span>{KIND_LABELS[deleteTarget.kind]}</span>
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
    </section>
  )
}
