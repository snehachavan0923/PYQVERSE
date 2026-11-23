import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { post, setSession } = vi.hoisted(() => ({
  post: vi.fn(),
  setSession: vi.fn(),
}))

vi.mock('../services/api', () => ({
  default: { post },
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    setSession,
    session: null,
  }),
}))

vi.mock('../services/notification', () => ({
  notification: {
    toast: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}))

import Login from './Login'
import Register from './Register'
import { afterEach } from 'vitest'

function renderInRouter(page: React.ReactNode) {
  return render(<BrowserRouter>{page}</BrowserRouter>)
}

describe('authentication forms', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    post.mockReset()
  })

  it('toggles login password visibility', () => {
    renderInRouter(<Login />)
    const password = document.querySelector('input[autocomplete="current-password"]') as HTMLInputElement
    expect(password).not.toBeNull()
    expect(password).toHaveAttribute('type', 'password')
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password).toHaveAttribute('type', 'text')
    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(password).toHaveAttribute('type', 'password')
  })

  it('toggles registration password visibility', () => {
    renderInRouter(<Register />)
    const password = document.querySelector('input[autocomplete="new-password"]') as HTMLInputElement
    expect(password).not.toBeNull()
    expect(password).toHaveAttribute('type', 'password')
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password).toHaveAttribute('type', 'text')
  })

  it('prevents duplicate password-login submissions', async () => {
    let resolveRequest!: (value: any) => void
    post.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve }))
    renderInRouter(<Login />)
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'student@rvce.edu.in' } })
    fireEvent.change(document.querySelector('input[autocomplete="current-password"]') as HTMLInputElement, { target: { value: 'password123' } })
    const button = screen.getByRole('button', { name: 'Sign in' })
    fireEvent.submit(button.closest('form')!)
    fireEvent.submit(button.closest('form')!)
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
    resolveRequest({
      data: {
        access_token: 'test',
        refresh_token: 'test',
        user: { id: 'test', email: 'student@rvce.edu.in', email_verified: true },
        profile: { id: 'test', role: 'STUDENT', onboarding_completed: true },
      },
    })
  })
})
