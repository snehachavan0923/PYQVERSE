import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import { openAdminDownload, openAdminPreview, type ContentKind } from '../services/contentApi'
import notifications from '../services/notification'
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

export default function AdminUploads() {
  const { session } = useAuth()
  const [data, setData] = useState<UploadResponse | null>(null)
  const [error, setError] = useState('')
  const [kindFilter, setKindFilter] = useState('')
  const [busy, setBusy] = useState<{ id: string; action: 'view' | 'download' } | null>(null)

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
    if (!kindFilter) return data.items
    return data.items.filter((item) => item.kind === kindFilter)
  }, [data, kindFilter])

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
                  <td>
                    <strong>{item.title}</strong>
                    {!item.active && <span className="table-subtext">Archived</span>}
                  </td>
                  <td>{item.subject_code ?? '—'}</td>
                  <td>{item.status === 'VERIFIED' ? 'Published' : item.status}</td>
                  <td>{formatSize(item.size)}</td>
                  <td>{formatDate(item.created_at)}</td>
                  <td>
                    <ContentActions
                      label={item.title}
                      busy={busy?.id === item.id}
                      viewDisabled={!isPdfFile(item.file_type)}
                      viewHint={isPdfFile(item.file_type) ? 'View PDF in a new tab' : 'Preview is available for PDF documents only'}
                      onView={() => void view(item)}
                      onDownload={() => void download(item)}
                    />
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
    </section>
  )
}
