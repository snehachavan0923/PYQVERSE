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

  describe('Email OTP flow', () => {
    it('switches between Password and Email OTP tabs', async () => {
      const user = userEvent.setup()
      renderLogin()

      expect(screen.getByRole('tab', { name: 'Password Login' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByLabelText('Password')).toBeInTheDocument()

      await user.click(screen.getByRole('tab', { name: 'Email OTP' }))

      expect(screen.getByRole('tab', { name: 'Email OTP' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByLabelText('Registered College Email')).toBeInTheDocument()
      expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()

      await user.click(screen.getByRole('tab', { name: 'Password Login' }))
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
    })

    it('requests an OTP and transitions to the 6-digit verification view', async () => {
      mocks.post.mockResolvedValue({
        data: { message: 'Verification code sent', email: 's*****@rvce.edu.in' },
      })
      const user = userEvent.setup()
      renderLogin()

      await user.click(screen.getByRole('tab', { name: 'Email OTP' }))
      await user.type(screen.getByLabelText('Registered College Email'), 'student@rvce.edu.in')
      await user.click(screen.getByRole('button', { name: 'Send Verification Code' }))

      expect(mocks.post).toHaveBeenCalledWith(
        '/auth/otp/request',
        { email: 'student@rvce.edu.in' },
        { timeout: 20_000 },
      )

      expect(await screen.findByText('s*****@rvce.edu.in')).toBeInTheDocument()
      expect(screen.getByText('Check your email')).toBeInTheDocument()
      expect(
        screen.getByText(/Check your inbox\. If you don't see it, check your Spam or Junk folder\./),
      ).toBeInTheDocument()
      expect(screen.getByRole('group', { name: '6-digit verification code' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Verify Code' })).toBeDisabled()
    })

    it('allows typing digits and auto-progressing through inputs', async () => {
      mocks.post.mockResolvedValueOnce({
        data: { message: 'Verification code sent', email: 's*****@rvce.edu.in' },
      })
      const user = userEvent.setup()
      renderLogin()

      await user.click(screen.getByRole('tab', { name: 'Email OTP' }))
      await user.type(screen.getByLabelText('Registered College Email'), 'student@rvce.edu.in')
      await user.click(screen.getByRole('button', { name: 'Send Verification Code' }))

      await screen.findByText('s*****@rvce.edu.in')

      const digit1 = screen.getByLabelText('Digit 1 of 6')
      const digit2 = screen.getByLabelText('Digit 2 of 6')
      const digit3 = screen.getByLabelText('Digit 3 of 6')
      const digit4 = screen.getByLabelText('Digit 4 of 6')
      const digit5 = screen.getByLabelText('Digit 5 of 6')
      const digit6 = screen.getByLabelText('Digit 6 of 6')

      await user.type(digit1, '1')
      expect(digit2).toHaveFocus()

      await user.type(digit2, '2')
      expect(digit3).toHaveFocus()

      await user.type(digit3, '3')
      await user.type(digit4, '4')
      await user.type(digit5, '5')
      await user.type(digit6, '6')

      expect(screen.getByRole('button', { name: 'Verify Code' })).toBeEnabled()
    })

    it('supports pasting a complete 6-digit OTP', async () => {
      mocks.post.mockResolvedValueOnce({
        data: { message: 'Verification code sent', email: 's*****@rvce.edu.in' },
      })
      mocks.post.mockResolvedValueOnce({ data: studentSession })
      const user = userEvent.setup()
      renderLogin()

      await user.click(screen.getByRole('tab', { name: 'Email OTP' }))
      await user.type(screen.getByLabelText('Registered College Email'), 'student@rvce.edu.in')
      await user.click(screen.getByRole('button', { name: 'Send Verification Code' }))

      await screen.findByText('s*****@rvce.edu.in')

      const digit1 = screen.getByLabelText('Digit 1 of 6')
      fireEvent.paste(digit1, {
        clipboardData: { getData: () => '123456' },
      })

      expect(screen.getByLabelText('Digit 1 of 6')).toHaveValue('1')
      expect(screen.getByLabelText('Digit 2 of 6')).toHaveValue('2')
      expect(screen.getByLabelText('Digit 3 of 6')).toHaveValue('3')
      expect(screen.getByLabelText('Digit 4 of 6')).toHaveValue('4')
      expect(screen.getByLabelText('Digit 5 of 6')).toHaveValue('5')
      expect(screen.getByLabelText('Digit 6 of 6')).toHaveValue('6')

      const verifyBtn = screen.getByRole('button', { name: 'Verify Code' })
      expect(verifyBtn).toBeEnabled()

      await user.click(verifyBtn)

      expect(mocks.post).toHaveBeenLastCalledWith(
        '/auth/otp/verify',
        { email: 'student@rvce.edu.in', token: '123456' },
        { timeout: 20_000 },
      )
      expect(await screen.findByText('Student dashboard route')).toBeInTheDocument()
      expect(mocks.setSession).toHaveBeenCalledWith(studentSession)
    })

    it('shows error when OTP verification fails', async () => {
      mocks.post.mockResolvedValueOnce({
        data: { message: 'Verification code sent', email: 's*****@rvce.edu.in' },
      })
      mocks.post.mockRejectedValueOnce({
        response: { status: 401, data: { detail: 'Invalid or expired verification code' } },
      })
      const user = userEvent.setup()
      renderLogin()

      await user.click(screen.getByRole('tab', { name: 'Email OTP' }))
      await user.type(screen.getByLabelText('Registered College Email'), 'student@rvce.edu.in')
      await user.click(screen.getByRole('button', { name: 'Send Verification Code' }))

      await screen.findByText('s*****@rvce.edu.in')

      const digit1 = screen.getByLabelText('Digit 1 of 6')
      fireEvent.paste(digit1, { clipboardData: { getData: () => '000000' } })

      await user.click(screen.getByRole('button', { name: 'Verify Code' }))

      await waitFor(() => {
        expect(mocks.error).toHaveBeenCalledWith('Verification failed', 'Invalid or expired verification code')
      })
      expect(screen.getByRole('alert')).toHaveTextContent('Invalid or expired verification code')
      expect(screen.getByRole('button', { name: 'Verify Code' })).toBeEnabled()
    })

    it('allows changing email with back button', async () => {
      mocks.post.mockResolvedValueOnce({
        data: { message: 'Verification code sent', email: 's*****@rvce.edu.in' },
      })
      const user = userEvent.setup()
      renderLogin()

      await user.click(screen.getByRole('tab', { name: 'Email OTP' }))
      await user.type(screen.getByLabelText('Registered College Email'), 'student@rvce.edu.in')
      await user.click(screen.getByRole('button', { name: 'Send Verification Code' }))

      await screen.findByText('s*****@rvce.edu.in')

      await user.click(screen.getByRole('button', { name: '← Change email' }))

      expect(screen.getByLabelText('Registered College Email')).toBeInTheDocument()
      expect(screen.queryByText('s*****@rvce.edu.in')).not.toBeInTheDocument()
    })
  })
})
