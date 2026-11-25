import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  toast: vi.fn(),
}))

vi.mock('../services/api', () => ({
  default: { get: mocks.get, post: mocks.post },
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    session: { access_token: 'token' },
    setSession: vi.fn(),
  }),
}))

vi.mock('../services/notification', () => ({
  default: { toast: mocks.toast },
}))

import Onboarding from '../pages/Onboarding'

beforeEach(() => {
  vi.clearAllMocks()
  mocks.get.mockImplementation((path: string, config?: { params?: { branch_id?: string } }) => {
    if (path === '/academic/branches') {
      return Promise.resolve({ data: [{ id: 'cse-id', code: 'CSE', name: 'Computer Science and Engineering' }] })
    }
    if (path === '/academic/schemes') {
      return Promise.resolve({ data: [{ id: 'scheme-id', code: '2025', name: '2025 Scheme' }] })
    }
    if (path === '/academic/semesters') {
      return Promise.resolve({ data: [{ id: 'semester-id', number: 3, name: 'Semester III', academic_scheme_id: 'scheme-id' }] })
    }
    if (path === '/subjects' && config?.params?.branch_id === 'cse-id') {
      return Promise.resolve({
        data: [{
          id: 'elective-id',
          code: 'CV232TA',
          name: 'Environment and Sustainability',
          subject_type: 'ELECTIVE',
          academic_scheme_id: 'scheme-id',
          semester_id: 'semester-id',
        }],
      })
    }
    return Promise.resolve({ data: [] })
  })
})

describe('Onboarding branch-scoped electives', () => {
  it('loads elective options for the selected branch without hiding the form', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <Onboarding />
      </MemoryRouter>,
    )

    await user.selectOptions(
      await screen.findByLabelText('Department'),
      'cse-id',
    )

    expect(await screen.findByRole('option', {
      name: 'CV232TA — Environment and Sustainability',
    })).toBeInTheDocument()
    expect(screen.getByLabelText('Academic scheme')).toBeInTheDocument()
    await waitFor(() => {
      expect(mocks.get).toHaveBeenCalledWith(
        '/subjects',
        { params: { branch_id: 'cse-id' } },
      )
    })
  })
})
