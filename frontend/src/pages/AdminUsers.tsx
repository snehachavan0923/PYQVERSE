import { useCallback, useEffect, useState, type FormEvent } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { PaginatedUsers } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'
import notifications from '../services/notification'

interface Option { id: string; name: string; code?: string; number?: number; academic_scheme_id?: string }
interface UserDetail {
  id: string
  full_name: string
  email: string
  role: string
  account_status: string
  email_verified: boolean
  created_at: string | null
  last_login_at: string | null
  student_profile: {
    usn: string | null
    profile_completed: boolean
    branch: string | null
    semester: string | null
    academic_scheme: string | null
    selected_elective: string | null
    enrollment_year: number | null
    enrolled_subjects: { id: string; code: string; name: string; is_elective: boolean }[]
  } | null
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString()
}

export default function AdminUsers() {
  const { session } = useAuth()
  const [data, setData] = useState<PaginatedUsers | null>(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const [branchId, setBranchId] = useState('')
  const [semesterId, setSemesterId] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [branches, setBranches] = useState<Option[]>([])
  const [semesters, setSemesters] = useState<Option[]>([])
  const [detail, setDetail] = useState<UserDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    Promise.all([api.get<Option[]>('/academic/branches'), api.get<Option[]>('/academic/semesters')])
      .then(([branchData, semesterData]) => {
        setBranches(branchData.data)
        setSemesters(semesterData.data)
      })
      .catch(() => undefined)
  }, [])

  const load = useCallback(() => {
    setError('')
    const params = new URLSearchParams({ page: String(page), page_size: '20' })
    if (role) params.set('role', role)
    if (status) params.set('status', status)
    if (branchId) params.set('branch_id', branchId)
    if (semesterId) params.set('semester_id', semesterId)
    if (search) params.set('search', search)
    getWithAuth<PaginatedUsers>(`/auth/admin/users?${params.toString()}`, session)
      .then(setData)
      .catch((err) => setError(errorDetail(err, 'Unable to load registered users')))
  }, [session, page, role, status, branchId, semesterId, search])

  useEffect(() => {
    load()
  }, [load])

  const submitSearch = (event: FormEvent) => {
    event.preventDefault()
    setPage(1)
    setSearch(searchInput.trim())
  }

  const openDetail = async (userId: string) => {
    setDetailLoading(true)
    try {
      const result = await getWithAuth<UserDetail>(`/auth/admin/users/${userId}`, session)
      setDetail(result)
    } catch (err) {
      void notifications.error('User detail unavailable', errorDetail(err, 'Unable to load user detail'))
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="User management"
        title="Registered users"
        description="View student profiles and account roles. Passwords and authentication secrets are never exposed."
      />

      <form className="filter-bar" onSubmit={submitSearch}>
        <label>
          Search
          <input type="search" placeholder="Name or email" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} />
        </label>
        <label>
          Role
          <select value={role} onChange={(event) => { setPage(1); setRole(event.target.value) }}>
            <option value="">All roles</option>
            <option value="STUDENT">Student</option>
            <option value="ADMIN_FACULTY">Admin / Faculty</option>
          </select>
        </label>
        <label>
          Status
          <select value={status} onChange={(event) => { setPage(1); setStatus(event.target.value) }}>
            <option value="">All statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
            <option value="SUSPENDED">Suspended</option>
          </select>
        </label>
        <label>
          Branch
          <select value={branchId} onChange={(event) => { setPage(1); setBranchId(event.target.value) }}>
            <option value="">All branches</option>
            {branches.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}
          </select>
        </label>
        <label>
          Semester
          <select value={semesterId} onChange={(event) => { setPage(1); setSemesterId(event.target.value) }}>
            <option value="">All semesters</option>
            {semesters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <button className="primary-button" type="submit">Apply</button>
      </form>

      {error && <ErrorState message={error} onRetry={load} />}
      {!data && !error && <LoadingState label="Loading users" rows={2} />}
      {data && (data.items.length ? (
        <>
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Branch / Semester</th>
                  <th>USN</th>
                  <th>Onboarding</th>
                  <th>Registered</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((user) => (
                  <tr key={user.id}>
                    <td><strong>{user.full_name}</strong></td>
                    <td>{user.email}</td>
                    <td><span className="type-pill">{user.role}</span></td>
                    <td>{user.account_status}</td>
                    <td>
                      {user.student_profile
                        ? <>{user.student_profile.branch_name ?? '—'}<span className="table-subtext">{user.student_profile.semester_name ?? '—'}</span></>
                        : '—'}
                    </td>
                    <td>{user.student_profile?.usn ?? '—'}</td>
                    <td>{user.student_profile ? (user.student_profile.profile_completed ? 'Complete' : 'Pending') : '—'}</td>
                    <td>{formatDate(user.created_at)}</td>
                    <td>
                      <button className="text-button" type="button" onClick={() => void openDetail(user.id)}>View</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination-bar">
            <span>{data.total} users · page {data.page} of {data.pages}</span>
            <div>
              <button className="secondary-button compact-button" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
              <button className="secondary-button compact-button" type="button" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          </div>
        </>
      ) : (
        <EmptyState title="No users found" description="No registered users match the current filters." />
      ))}

      {detailLoading && <LoadingState label="Loading user detail" rows={1} />}
      {detail && (
        <article className="editor-panel" aria-live="polite">
          <div className="section-heading">
            <h2>{detail.full_name}</h2>
            <button className="secondary-button compact-button" type="button" onClick={() => setDetail(null)}>Close</button>
          </div>
          <div className="detail-row"><span>Email</span><strong>{detail.email}</strong></div>
          <div className="detail-row"><span>Role</span><strong>{detail.role}</strong></div>
          <div className="detail-row"><span>Status</span><strong>{detail.account_status}</strong></div>
          <div className="detail-row"><span>Email verified</span><strong>{detail.email_verified ? 'Yes' : 'No'}</strong></div>
          <div className="detail-row"><span>Registered</span><strong>{formatDate(detail.created_at)}</strong></div>
          <div className="detail-row"><span>Last login</span><strong>{formatDate(detail.last_login_at)}</strong></div>
          {detail.student_profile && (
            <>
              <div className="detail-row"><span>USN</span><strong>{detail.student_profile.usn ?? 'Not provided'}</strong></div>
              <div className="detail-row"><span>Branch</span><strong>{detail.student_profile.branch ?? 'Not set'}</strong></div>
              <div className="detail-row"><span>Semester</span><strong>{detail.student_profile.semester ?? 'Not set'}</strong></div>
              <div className="detail-row"><span>Academic scheme</span><strong>{detail.student_profile.academic_scheme ?? 'Not set'}</strong></div>
              <div className="detail-row"><span>Selected elective</span><strong>{detail.student_profile.selected_elective ?? 'None'}</strong></div>
              <div className="detail-row"><span>Enrollment year</span><strong>{detail.student_profile.enrollment_year ?? 'Not set'}</strong></div>
              <div className="detail-row">
                <span>Enrolled subjects</span>
                <strong>{detail.student_profile.enrolled_subjects.length ? detail.student_profile.enrolled_subjects.map((subject) => subject.code).join(', ') : 'None'}</strong>
              </div>
            </>
          )}
        </article>
      )}
    </section>
  )
}
