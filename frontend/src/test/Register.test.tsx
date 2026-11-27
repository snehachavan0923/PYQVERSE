import { fireEvent, render, screen } from '@testing-library/react'
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

import Register from '../pages/Register'

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="/login" element={<div>Login page route</div>} />
        <Route path="/onboarding" element={<div>Onboarding page route</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Register flow', () => {
  it('rejects non-RVCE email address', async () => {
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('Full name'), 'New Student')
    await user.type(screen.getByLabelText('RVCE email'), 'student@gmail.com')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.type(screen.getByLabelText('Confirm password'), 'StrongPass1')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(
      screen.getByText('Student registration requires an @rvce.edu.in email address.'),
    ).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('rejects passwords that do not match', async () => {
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('Full name'), 'New Student')
    await user.type(screen.getByLabelText('RVCE email'), 'student@rvce.edu.in')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.type(screen.getByLabelText('Confirm password'), 'DifferentPass2')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('shows confirmation screen with 6-digit OTP input upon successful signup', async () => {
    mocks.post.mockResolvedValueOnce({
      data: {
        email_verification_pending: true,
        user: { id: 'u1', email: 'new.student@rvce.edu.in', email_verified: false },
        profile: { id: 'p1', role: 'STUDENT', onboarding_completed: false },
      },
    })
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('Full name'), 'New Student')
    await user.type(screen.getByLabelText('RVCE email'), 'new.student@rvce.edu.in')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.type(screen.getByLabelText('Confirm password'), 'StrongPass1')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(mocks.post).toHaveBeenCalledWith('/auth/register', {
      email: 'new.student@rvce.edu.in',
      password: 'StrongPass1',
      confirm_password: 'StrongPass1',
      full_name: 'New Student',
    })

    expect(await screen.findByText('Please verify your email')).toBeInTheDocument()
    expect(screen.getByText('Check your email')).toBeInTheDocument()
    expect(
      screen.getByText(/Check your inbox\. If you don't see it, check your Spam or Junk folder\./),
    ).toBeInTheDocument()
    expect(screen.getByText('n*****@rvce.edu.in')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: '6-digit verification code' })).toBeInTheDocument()
  })

  it('allows activating account by entering 6-digit OTP code directly on confirmation screen', async () => {
    mocks.post.mockResolvedValueOnce({
      data: {
        email_verification_pending: true,
        user: { id: 'u1', email: 'new.student@rvce.edu.in', email_verified: false },
        profile: { id: 'p1', role: 'STUDENT', onboarding_completed: false },
      },
    })
    mocks.post.mockResolvedValueOnce({
      data: {
        access_token: 'valid-access',
        refresh_token: 'valid-refresh',
        user: { id: 'u1', email: 'new.student@rvce.edu.in', email_verified: true },
        profile: { id: 'p1', role: 'STUDENT', onboarding_completed: false },
      },
    })
    const user = userEvent.setup()
    renderRegister()

    await user.type(screen.getByLabelText('Full name'), 'New Student')
    await user.type(screen.getByLabelText('RVCE email'), 'new.student@rvce.edu.in')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.type(screen.getByLabelText('Confirm password'), 'StrongPass1')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await screen.findByText('Please verify your email')

    const digit1 = screen.getByLabelText('Digit 1 of 6')
    fireEvent.paste(digit1, { clipboardData: { getData: () => '123456' } })

    const verifyBtn = screen.getByRole('button', { name: 'Verify & Activate Account' })
    expect(verifyBtn).toBeEnabled()
    await user.click(verifyBtn)

    expect(mocks.post).toHaveBeenLastCalledWith(
      '/auth/otp/verify',
      { email: 'new.student@rvce.edu.in', token: '123456' },
      { timeout: 20_000 },
    )
    expect(await screen.findByText('Onboarding page route')).toBeInTheDocument()
    expect(mocks.setSession).toHaveBeenCalled()
  })
})
