import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

export default function UserManagement() {
  const { session } = useAuth()
  const [users, setUsers] = useState<any[]>([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/admin/users', {
      headers: { Authorization: `Bearer ${session?.access_token}` },
      params: { search, page: 1, page_size: 20 },
    }).then((response) => setUsers(response.data.items ?? []))
      .catch((err) => setError(err.response?.data?.detail ?? 'Unable to load users'))
  }, [session?.access_token, search])

  return (
    <section className="dashboard-shell">
      <header className="dashboard-header"><div><p className="eyebrow">Administration</p><h1>User management</h1></div></header>
      <article className="dashboard-card wide">
        <label>Search users<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or email" /></label>
        {error && <p className="form-error">{error}</p>}
        {!error && users.length === 0 && <p className="muted">No registered users match this search.</p>}
        {users.length > 0 && <div className="subject-list">{users.map((user) => <div key={user.id}><strong>{user.full_name}</strong><span>{user.email} · {user.role}</span></div>)}</div>}
      </article>
    </section>
  )
}
