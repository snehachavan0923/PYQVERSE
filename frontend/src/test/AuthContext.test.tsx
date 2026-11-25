import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  signOut: vi.fn(),
  toast: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('../services/api', () => ({
  default: { get: mocks.get, post: mocks.post },
  SESSION_EXPIRED_EVENT: 'pyqverse:session-expired',
}))
vi.mock('../services/supabase', () => ({
  supabase: {
    auth: {
      onAuthStateChange: () => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
      signOut: mocks.signOut,
    },
  },
}))
vi.mock('../services/notification', () => ({
  default: { toast: mocks.toast, warning: mocks.warning },
}))

import { AuthProvider, useAuth } from '../context/AuthContext'

const storedSession = {
  access_token: 'old-session-token',
  refresh_token: 'old-refresh-token',
  user: { id: 'user-id', email: 'student@rvce.edu.in', email_verified: true },
  profile: { id: 'profile-id', role: 'STUDENT', onboarding_completed: true },
}

function StateView({ children }: { children?: ReactNode }) {
  const { session, loading, restoreError, retryRestore } = useAuth()
  return (
    <div>
      <span>{loading ? 'initializing' : 'initialized'}</span>
      <span>{session?.profile.role ?? 'signed-out'}</span>
      {restoreError && <p role="alert">{restoreError}</p>}
      <button type="button" onClick={retryRestore}>Retry session restore</button>
      {children}
    </div>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('AuthProvider session restoration', () => {
  it('keeps the saved session and offers retry after a transient server failure', async () => {
    localStorage.setItem('pyqverse_session', JSON.stringify(storedSession))
    mocks.post
      .mockRejectedValueOnce({
        response: { status: 503, data: { detail: 'Auth service unavailable' } },
      })
      .mockResolvedValueOnce({
        data: {
          access_token: 'new-access-token',
          refresh_token: 'new-refresh-token',
          user: storedSession.user,
        },
      })
    mocks.get.mockResolvedValue({
      data: { id: 'user-id', role: 'STUDENT', onboarding_completed: true },
    })
    render(<AuthProvider><StateView /></AuthProvider>)

    expect(await screen.findByText('Auth service unavailable')).toBeInTheDocument()
    expect(screen.getByText('initialized')).toBeInTheDocument()
    expect(localStorage.getItem('pyqverse_session')).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Retry session restore' }))
    await waitFor(() => expect(screen.getByText('STUDENT')).toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('clears a stored session rejected as expired', async () => {
    localStorage.setItem('pyqverse_session', JSON.stringify(storedSession))
    mocks.post.mockRejectedValue({
      response: { status: 401, data: { detail: 'Invalid or expired session' } },
    })
    render(<AuthProvider><StateView /></AuthProvider>)

    await waitFor(() => expect(screen.getByText('signed-out')).toBeInTheDocument())
    expect(localStorage.getItem('pyqverse_session')).toBeNull()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
