import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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
  mocks.get.mockImplementation((path: string, config?: { params?: { branch_id?: string; scheme_id?: string; semester_id?: string } }) => {
    if (path === '/academic/branches') {
      return Promise.resolve({ data: [{ id: 'cse-id', code: 'CSE', name: 'Computer Science and Engineering' }] })
    }
    if (path === '/academic/schemes') {
      return Promise.resolve({ data: [{ id: 'scheme-id', code: '2025', name: '2025 Scheme' }] })
    }
    if (path === '/academic/semesters') {
      return Promise.resolve({ data: [
        { id: 'semester-id', number: 3, name: 'Semester III', academic_scheme_id: 'scheme-id' },
        { id: 'semester-4-id', number: 4, name: 'Semester IV', academic_scheme_id: 'scheme-id' },
      ] })
    }
    if ((path === '/academic/electives' || path === '/subjects') &&
        config?.params?.branch_id === 'cse-id' &&
        config?.params?.scheme_id === 'scheme-id' &&
        config?.params?.semester_id === 'semester-id') {
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

describe('Onboarding electives flow', () => {
  it('loads elective options when department, scheme, and semester are selected', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <Onboarding />
      </MemoryRouter>,
    )

    // Select Department
    await user.selectOptions(await screen.findByLabelText('Department'), 'cse-id')
    // Select Academic scheme
    await user.selectOptions(screen.getByLabelText('Academic scheme'), 'scheme-id')
    // Select Current semester
    await user.selectOptions(screen.getByLabelText('Current semester'), 'semester-id')

    expect(await screen.findByRole('option', {
      name: 'CV232TA — Environment and Sustainability',
    })).toBeInTheDocument()

    // Elective is optional - "No elective selected" exists
    expect(screen.getByRole('option', { name: 'No elective selected' })).toBeInTheDocument()
  })

  it('shows clear empty state when no electives exist for the selected semester', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <Onboarding />
      </MemoryRouter>,
    )

    await user.selectOptions(await screen.findByLabelText('Department'), 'cse-id')
    await user.selectOptions(screen.getByLabelText('Academic scheme'), 'scheme-id')
    // Select Semester IV which has no electives in mock
    await user.selectOptions(screen.getByLabelText('Current semester'), 'semester-4-id')

    expect(await screen.findByRole('option', {
      name: 'No electives available for this semester',
    })).toBeInTheDocument()
  })

  it('clears selected elective when scheme or semester changes', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <Onboarding />
      </MemoryRouter>,
    )

    await user.selectOptions(await screen.findByLabelText('Department'), 'cse-id')
    await user.selectOptions(screen.getByLabelText('Academic scheme'), 'scheme-id')
    await user.selectOptions(screen.getByLabelText('Current semester'), 'semester-id')

    await user.selectOptions(
      screen.getByLabelText('Selected elective (optional)'),
      'elective-id',
    )
    expect((screen.getByLabelText('Selected elective (optional)') as HTMLSelectElement).value).toBe('elective-id')

    // Change semester
    await user.selectOptions(screen.getByLabelText('Current semester'), 'semester-4-id')
    expect((screen.getByLabelText('Selected elective (optional)') as HTMLSelectElement).value).toBe('')
  })
})
