import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import type { PaginatedUsers } from '../types/dashboard'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'

export default function AdminUsers() {
  const { session } = useAuth()
  const [data, setData] = useState<PaginatedUsers | null>(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [role, setRole] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    const params = new URLSearchParams({ page: String(page), page_size: '20' })
    if (role) params.set('role', role)
    if (search) params.set('search', search)
    getWithAuth<PaginatedUsers>(`/auth/admin/users?${params.toString()}`, session)
      .then(setData)
      .catch((err) => setError(errorDetail(err, 'Unable to load registered users')))
  }, [session, page, role, search])

  const submitSearch = (event: FormEvent) => {
    event.preventDefault()
    setPage(1)
    setSearch(searchInput.trim())
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
          <input
            type="search"
            placeholder="Name or email"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </label>
        <label>
          Role
          <select
            value={role}
            onChange={(event) => {
              setPage(1)
              setRole(event.target.value)
            }}
          >
            <option value="">All roles</option>
            <option value="STUDENT">Student</option>
            <option value="ADMIN_FACULTY">Admin / Faculty</option>
          </select>
        </label>
        <button className="primary-button" type="submit">Search</button>
      </form>

      {error && <p className="form-error">{error}</p>}
      {!data && !error && <div className="pyq-loading">Loading users...</div>}
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
                  <th>USN</th>
                  <th>Onboarding</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((user) => (
                  <tr key={user.id}>
                    <td><strong>{user.full_name}</strong></td>
                    <td>{user.email}</td>
                    <td><span className="type-pill">{user.role}</span></td>
                    <td>{user.account_status}</td>
                    <td>{user.student_profile?.usn ?? '—'}</td>
                    <td>{user.student_profile ? (user.student_profile.profile_completed ? 'Complete' : 'Pending') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination-bar">
            <span>{data.total} users · page {data.page} of {data.pages}</span>
            <div>
              <button className="secondary-button compact-button" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <button className="secondary-button compact-button" type="button" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>
                Next
              </button>
            </div>
          </div>
        </>
      ) : (
        <EmptyState title="No users found" description="No registered users match the current filters." />
      ))}
    </section>
  )
}
