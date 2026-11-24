import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ProtectedRoute from '../components/ProtectedRoute'

const authState = vi.hoisted(() => ({
  session: null as Record<string, unknown> | null,
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ session: authState.session, loading: false }),
}))

vi.mock('../services/notification', () => ({
  default: {
    warning: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    toast: vi.fn(),
    confirm: vi.fn(),
  },
}))

function makeSession(role: 'STUDENT' | 'ADMIN_FACULTY', onboardingCompleted = true) {
  return {
    access_token: 'token',
    refresh_token: 'refresh',
    user: { email: 'student@rvce.edu.in', email_verified: true },
    profile: { id: 'profile', role, onboarding_completed: onboardingCompleted },
  }
}

function renderAdminRoute() {
  return render(
    <MemoryRouter initialEntries={['/admin']}>
      <Routes>
        <Route element={<ProtectedRoute role="ADMIN_FACULTY" />}>
          <Route path="/admin" element={<div>Admin area</div>} />
        </Route>
        <Route path="/student" element={<div>Student area</div>} />
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  authState.session = makeSession('STUDENT')
})

describe('ProtectedRoute role enforcement', () => {
  it('redirects a student away from admin routes', () => {
    renderAdminRoute()
    expect(screen.getByText('Student area')).toBeInTheDocument()
    expect(screen.queryByText('Admin area')).not.toBeInTheDocument()
  })

  it('allows an administrator into admin routes', () => {
    authState.session = makeSession('ADMIN_FACULTY')
    renderAdminRoute()
    expect(screen.getByText('Admin area')).toBeInTheDocument()
  })

  it('redirects an unauthenticated visitor to login', () => {
    authState.session = null
    renderAdminRoute()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })
})
