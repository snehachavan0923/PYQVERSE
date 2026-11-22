import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import ThemeToggle from '../components/ThemeToggle'
import { useAuth } from '../context/AuthContext'

interface NavItem {
  label: string
  to: string
  end?: boolean
}

const studentNavigation: NavItem[] = [
  { label: 'Dashboard', to: '/student', end: true },
  { label: 'My Subjects', to: '/student/subjects' },
  { label: 'Syllabus', to: '/student/syllabus' },
  { label: 'Previous Year Questions', to: '/student/pyqs' },
  { label: 'Learning Resources', to: '/student/resources' },
  { label: 'Profile', to: '/student/profile' },
  { label: 'Settings', to: '/student/settings' },
]

const adminNavigation: NavItem[] = [
  { label: 'Overview', to: '/admin', end: true },
  { label: 'Academic Management', to: '/admin/academic' },
  { label: 'User Management', to: '/admin/users' },
  { label: 'Syllabus Management', to: '/admin/syllabus' },
  { label: 'PYQ Management', to: '/admin/pyqs' },
  { label: 'Learning Resources', to: '/admin/resources' },
  { label: 'Uploads', to: '/admin/uploads' },
  { label: 'Profile', to: '/admin/profile' },
  { label: 'Settings', to: '/admin/settings' },
]

export default function DashboardLayout({ role }: { role: 'STUDENT' | 'ADMIN_FACULTY' }) {
  const { session, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const navigation = role === 'ADMIN_FACULTY' ? adminNavigation : studentNavigation
  const roleLabel = role === 'ADMIN_FACULTY' ? 'Admin / Faculty' : 'Student'

  return (
    <div className="dashboard-layout">
      <aside className={`sidebar${menuOpen ? ' sidebar-open' : ''}`}>
        <div className="sidebar-brand">
          <span className="brand-badge">PYQ</span>
          <div>
            <strong>PYQVERSE</strong>
            <small>{roleLabel}</small>
          </div>
        </div>
        <nav className="sidebar-nav">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="sidebar-email">{session?.user.email}</span>
          <button className="secondary-button" type="button" onClick={() => void logout()}>
            Log out
          </button>
        </div>
      </aside>
      {menuOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <div className="dashboard-main">
        <header className="dashboard-topbar">
          <button className="menu-button" type="button" onClick={() => setMenuOpen(true)}>
            Menu
          </button>
          <div className="topbar-title">
            <span className="eyebrow">PYQVERSE Workspace</span>
          </div>
          <ThemeToggle />
        </header>
        <main className="dashboard-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
