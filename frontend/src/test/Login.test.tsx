import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  setSession: vi.fn(),
  toast: vi.fn(),
  error: vi.fn(),
}))

vi.mock('../services/api', () => ({ default: { post: mocks.post } }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ setSession: mocks.setSession }),
}))
vi.mock('../services/notification', () => ({
  default: { toast: mocks.toast, error: mocks.error },
}))

import Login from '../pages/Login'

const studentSession = {
  access_token: 'student-access',
  refresh_token: 'student-refresh',
  user: { id: 'student-id', email: 'student@rvce.edu.in', email_verified: true },
  profile: { id: 'student-profile', role: 'STUDENT' as const, onboarding_completed: true },
}

const adminSession = {
  ...studentSession,
  user: { ...studentSession.user, email: 'admin@example.com' },
  profile: { id: 'admin-profile', role: 'ADMIN_FACULTY' as const, onboarding_completed: false },
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/student" element={<div>Student dashboard route</div>} />
        <Route path="/admin" element={<div>Admin dashboard route</div>} />
        <Route path="/onboarding" element={<div>Student onboarding route</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Login flow', () => {
  it('stores a student session and navigates to the student dashboard', async () => {
    mocks.post.mockResolvedValue({ data: studentSession })
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'student@rvce.edu.in')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Student dashboard route')).toBeInTheDocument()
    expect(mocks.setSession).toHaveBeenCalledWith(studentSession)
    expect(mocks.post).toHaveBeenCalledWith(
      '/auth/login',
      { email: 'student@rvce.edu.in', password: 'StrongPass1' },
      { timeout: 20_000 },
    )
  })

  it('stores an admin session and navigates to the admin dashboard', async () => {
    mocks.post.mockResolvedValue({ data: adminSession })
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'admin@example.com')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Admin dashboard route')).toBeInTheDocument()
    expect(mocks.setSession).toHaveBeenCalledWith(adminSession)
  })

  it('shows invalid credentials and resets loading after failure', async () => {
    mocks.post.mockRejectedValue({
      response: { status: 401, data: { detail: 'Invalid email or password' } },
    })
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'student@rvce.edu.in')
    await user.type(screen.getByLabelText('Password'), 'WrongPass1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => {
      expect(mocks.error).toHaveBeenCalledWith('Sign-in failed', 'Invalid email or password')
    })
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
    expect(mocks.setSession).not.toHaveBeenCalled()
  })

  it('shows a timeout notification and resets the loading button', async () => {
    mocks.post.mockRejectedValue({ code: 'ECONNABORTED' })
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'student@rvce.edu.in')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => {
      expect(mocks.error).toHaveBeenCalledWith(
        'Sign-in failed',
        'The request took too long to complete. Check your connection and try again.',
      )
    })
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
  })

  it('prevents duplicate submissions while the login request is pending', async () => {
    let resolveLogin!: (value: { data: typeof studentSession }) => void
    mocks.post.mockImplementation(
      () => new Promise((resolve) => { resolveLogin = resolve }),
    )
    renderLogin()

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'student@rvce.edu.in' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'StrongPass1' },
    })
    const form = screen.getByRole('button', { name: 'Sign in' }).closest('form')
    expect(form).not.toBeNull()
    fireEvent.submit(form!)
    fireEvent.submit(form!)

    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Signing in…' })).toBeDisabled()

    await act(async () => {
      resolveLogin({ data: studentSession })
    })
    expect(await screen.findByText('Student dashboard route')).toBeInTheDocument()
  })

  it('routes a newly signed-in student to onboarding', async () => {
    mocks.post.mockResolvedValue({
      data: {
        ...studentSession,
        profile: { ...studentSession.profile, onboarding_completed: false },
      },
    })
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'student@rvce.edu.in')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Student onboarding route')).toBeInTheDocument()
  })
})
