import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import { openAdminDownload, type ContentKind } from '../services/contentApi'
import notifications from '../services/notification'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

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
  const [busyId, setBusyId] = useState('')

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

  const download = async (item: UploadItem) => {
    setBusyId(item.id)
    try {
      const url = await openAdminDownload(session, downloadKind(item.kind), item.id)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      void notifications.error('Download unavailable', errorDetail(err, 'The file could not be opened'))
    } finally {
      setBusyId('')
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
                    <button
                      className="text-button"
                      type="button"
                      disabled={busyId === item.id}
                      onClick={() => void download(item)}
                    >
                      {busyId === item.id ? 'Opening…' : 'Download'}
                    </button>
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
