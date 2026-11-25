import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWithAuth: vi.fn(),
  session: { access_token: 'test-session-token' },
}))

vi.mock('../services/authApi', () => ({
  getWithAuth: mocks.getWithAuth,
  errorDetail: (error: { message?: string }, fallback: string) => error.message ?? fallback,
}))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ session: mocks.session }),
}))

import AdminDashboard from '../pages/AdminDashboard'
import StudentDashboard from '../pages/StudentDashboard'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('dashboard request states', () => {
  it('renders the student empty state for a successful empty catalog response', async () => {
    mocks.getWithAuth.mockResolvedValue({
      welcome_name: 'Student',
      profile: {},
      academic_overview: {},
      subjects: [],
    })
    render(<MemoryRouter><StudentDashboard /></MemoryRouter>)

    expect(await screen.findByText('No subjects enrolled yet')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows malformed student responses and allows retry', async () => {
    mocks.getWithAuth
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({
        welcome_name: 'Student',
        profile: {},
        academic_overview: {},
        subjects: [],
      })
    render(<MemoryRouter><StudentDashboard /></MemoryRouter>)

    expect(await screen.findByText('The server returned an incomplete dashboard. Please retry.'))
      .toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('No subjects enrolled yet')).toBeInTheDocument()
    expect(mocks.getWithAuth).toHaveBeenCalledTimes(2)
  })

  it('shows admin API failures and clears the dashboard loading state', async () => {
    mocks.getWithAuth.mockRejectedValue(new Error('Dashboard service unavailable'))
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>)

    expect(await screen.findByText('Dashboard service unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
    await waitFor(() => expect(screen.queryByText('Loading administration statistics')).not.toBeInTheDocument())
  })

  it('renders empty admin statistics and activity without missing-field failures', async () => {
    mocks.getWithAuth.mockResolvedValue({
      welcome_name: 'Administrator',
      catalog_overview: {},
      user_overview: {},
      document_overview: {},
    })
    render(<MemoryRouter><AdminDashboard /></MemoryRouter>)

    expect(await screen.findByText('Welcome, Administrator')).toBeInTheDocument()
    expect(screen.getByText('No recent activity')).toBeInTheDocument()
    expect(screen.getAllByText('0').length).toBeGreaterThan(0)
  })
})
