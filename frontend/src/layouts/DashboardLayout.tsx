import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import ThemeToggle from '../components/ThemeToggle'
import { useAuth } from '../context/AuthContext'
import notifications from '../services/notification'

type IconName =
  | 'dashboard'
  | 'subjects'
  | 'syllabus'
  | 'questions'
  | 'resources'
  | 'profile'
  | 'settings'
  | 'overview'
  | 'academic'
  | 'users'
  | 'uploads'

interface NavItem {
  label: string
  to: string
  end?: boolean
  icon: IconName
}

const studentNavigation: NavItem[] = [
  { label: 'Dashboard', to: '/student', end: true, icon: 'dashboard' },
  { label: 'My Subjects', to: '/student/subjects', icon: 'subjects' },
  { label: 'Syllabus', to: '/student/syllabus', icon: 'syllabus' },
  { label: 'Previous Year Questions', to: '/student/pyqs', icon: 'questions' },
  { label: 'Learning Resources', to: '/student/resources', icon: 'resources' },
  { label: 'Profile', to: '/student/profile', icon: 'profile' },
  { label: 'Settings', to: '/student/settings', icon: 'settings' },
]

const adminNavigation: NavItem[] = [
  { label: 'Overview', to: '/admin', end: true, icon: 'overview' },
  { label: 'Academic Management', to: '/admin/academic', icon: 'academic' },
  { label: 'User Management', to: '/admin/users', icon: 'users' },
  { label: 'Syllabus Management', to: '/admin/syllabus', icon: 'syllabus' },
  { label: 'PYQ Management', to: '/admin/pyqs', icon: 'questions' },
  { label: 'Learning Resources', to: '/admin/resources', icon: 'resources' },
  { label: 'Uploads', to: '/admin/uploads', icon: 'uploads' },
  { label: 'Profile', to: '/admin/profile', icon: 'profile' },
  { label: 'Settings', to: '/admin/settings', icon: 'settings' },
]

const PATHS: Record<IconName, string> = {
  dashboard: 'M3 10.5 12 3l9 7.5M5 9.5V21h5v-6h4v6h5V9.5',
  subjects: 'M4 5.5A2.5 2.5 0 0 1 6.5 3H20v18H6.5A2.5 2.5 0 0 1 4 18.5v-13ZM4 17.5h16',
  syllabus: 'M7 3h10a2 2 0 0 1 2 2v16H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2ZM9 7h6M9 11h6M9 15h4',
  questions: 'M9 3h6l4 4v12a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2ZM14 3v5h5M10 13h4M10 17h3',
  resources: 'M4 5a2 2 0 0 1 2-2h5l2 2h5a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5Z',
  profile: 'M20 21a8 8 0 1 0-16 0M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.98 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 8.98a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9A1.7 1.7 0 0 0 10.03 3.1V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9c.14.6.7 1.03 1.34 1.03H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.56 1.03Z',
  overview: 'M4 4h7v7H4V4ZM13 4h7v4h-7V4ZM13 10h7v10h-7V10ZM4 13h7v7H4v-7Z',
  academic: 'M22 10 12 5 2 10l10 5 10-5ZM6 12v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5',
  users: 'M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  uploads: 'M12 16V4M7 9l5-5 5 5M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3',
}

function NavIcon({ name }: { name: IconName }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}

function BrandMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H12v16H6.5A2.5 2.5 0 0 1 4 17.5v-11Z" />
      <path d="M20 6.5A2.5 2.5 0 0 0 17.5 4H12v16h5.5a2.5 2.5 0 0 0 2.5-2.5v-11Z" />
      <path d="M12 8v8" />
    </svg>
  )
}

function LogoutIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5M21 12H9" />
    </svg>
  )
}

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  )
}

function initialsOf(email: string | undefined) {
  if (!email) return 'PY'
  const local = email.split('@')[0] ?? ''
  const parts = local.split(/[._-]+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return local.slice(0, 2).toUpperCase() || 'PY'
}

export default function DashboardLayout({ role }: { role: 'STUDENT' | 'ADMIN_FACULTY' }) {
  const { session, logout } = useAuth()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const navigation = role === 'ADMIN_FACULTY' ? adminNavigation : studentNavigation
  const roleLabel = role === 'ADMIN_FACULTY' ? 'Admin / Faculty' : 'Student'
  const email = session?.user.email
  const profilePath = role === 'ADMIN_FACULTY' ? '/admin/profile' : '/student/profile'

  const activeItem =
    [...navigation]
      .sort((a, b) => b.to.length - a.to.length)
      .find((item) => location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)) ??
    navigation[0]

  const confirmLogout = async () => {
    const confirmed = await notifications.confirm({
      title: 'Log out of PYQVERSE?',
      text: 'You will need to sign in again to access your workspace.',
      confirmText: 'Log out',
    })
    if (confirmed) await logout()
  }

  return (
    <div className="dashboard-layout">
      <aside className={`sidebar${menuOpen ? ' sidebar-open' : ''}`}>
        <div className="sidebar-brand">
          <span className="brand-badge">
            <BrandMark />
          </span>
          <div>
            <strong>PYQVERSE</strong>
            <small>{roleLabel}</small>
          </div>
          <button
            className="menu-button sidebar-close"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
          >
            <CloseIcon />
          </button>
        </div>
        <nav className="sidebar-nav" aria-label={`${roleLabel} navigation`}>
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              <span className="sidebar-link-icon">
                <NavIcon name={item.icon} />
              </span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-user">
            <span className="sidebar-avatar" aria-hidden="true">{initialsOf(email)}</span>
            <div className="sidebar-user-info">
              <strong>{roleLabel}</strong>
              <span className="sidebar-email">{email}</span>
            </div>
          </div>
          <button className="sidebar-logout" type="button" onClick={() => void confirmLogout()}>
            <LogoutIcon />
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
          <button
            className="menu-button"
            type="button"
            aria-label="Open navigation"
            onClick={() => setMenuOpen(true)}
          >
            <MenuIcon />
          </button>
          <div className="topbar-context">
            <span className="topbar-eyebrow">
              {role === 'ADMIN_FACULTY' ? 'Administration' : 'Student workspace'}
            </span>
            <span className="topbar-title-main">{activeItem.label}</span>
          </div>
          <div className="topbar-actions">
            <ThemeToggle />
            <Link className="avatar-button" to={profilePath} aria-label="Open profile">
              {initialsOf(email)}
            </Link>
          </div>
        </header>
        <main className="dashboard-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
