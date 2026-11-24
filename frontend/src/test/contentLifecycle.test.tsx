import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mocks = vi.hoisted(() => ({
  listAdminContent: vi.fn(),
  updateAdminContent: vi.fn(),
  archiveAdminContent: vi.fn(),
  uploadAdminContent: vi.fn(),
  openAdminPreview: vi.fn(),
  openAdminDownload: vi.fn(),
  confirm: vi.fn(),
  toast: vi.fn(),
  error: vi.fn(),
  retryError: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ session: { access_token: 'token' } }),
}))

vi.mock('../hooks/useAdminSubjects', () => ({
  useAdminSubjects: () => [],
}))

vi.mock('../services/contentApi', () => ({
  listAdminContent: mocks.listAdminContent,
  updateAdminContent: mocks.updateAdminContent,
  archiveAdminContent: mocks.archiveAdminContent,
  uploadAdminContent: mocks.uploadAdminContent,
  openAdminPreview: mocks.openAdminPreview,
  openAdminDownload: mocks.openAdminDownload,
}))

vi.mock('../services/notification', () => ({
  default: {
    confirm: mocks.confirm,
    toast: mocks.toast,
    error: mocks.error,
    retryError: mocks.retryError,
  },
}))

import AdminContentManager from '../pages/AdminContentManager'

const session = { access_token: 'token' }

const draft = {
  id: 'draft-1',
  subject_id: 'subject-1',
  subject_code: 'CS233AI',
  subject_name: 'Data Structures',
  original_filename: 'draft-paper.pdf',
  file_type: 'pdf',
  title: 'Draft paper',
  description: null,
  exam_type: 'SEE',
  cie_number: null,
  examination_year: 2025,
  verification_status: 'DRAFT',
  active: true,
}

const archived = {
  ...draft,
  id: 'archived-1',
  title: 'Archived paper',
  verification_status: 'VERIFIED',
  active: false,
}

beforeEach(() => {
  vi.restoreAllMocks()
  Object.values(mocks).forEach((mock) => mock.mockReset())
  mocks.listAdminContent.mockResolvedValue({ items: [draft, archived], total: 2 })
  mocks.updateAdminContent.mockResolvedValue({})
  mocks.archiveAdminContent.mockResolvedValue({ message: 'archived' })
  mocks.uploadAdminContent.mockResolvedValue({})
  mocks.confirm.mockResolvedValue(true)
  mocks.retryError.mockResolvedValue(false)
})

describe('AdminContentManager lifecycle states', () => {
  it('shows DRAFT for an active draft and a Publish action', async () => {
    render(<AdminContentManager kind="pyq" />)

    expect(await screen.findByText('Draft paper')).toBeInTheDocument()
    expect(screen.getByText('DRAFT')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Publish' })).toBeInTheDocument()
  })

  it('shows ARCHIVED separately from its publication status', async () => {
    const { container } = render(<AdminContentManager kind="pyq" />)

    expect(await screen.findByText('Archived paper')).toBeInTheDocument()
    expect(container.querySelector('.tag-archived')).toHaveTextContent('Archived')
    expect(screen.getByText('Publication: Published')).toBeInTheDocument()
    expect(container.querySelector('.tag-published')).toBeNull()
  })

  it('publishes a draft with an explicit reactivation', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)

    await user.click(await screen.findByRole('button', { name: 'Publish' }))
    await waitFor(() =>
      expect(mocks.updateAdminContent).toHaveBeenCalledWith(
        session,
        'pyq',
        'draft-1',
        { status: 'VERIFIED', active: true },
      ),
    )
  })

  it('archives an active record after confirmation', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)

    await user.click(await screen.findByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(mocks.confirm).toHaveBeenCalled())
    expect(mocks.archiveAdminContent).toHaveBeenCalledWith(session, 'pyq', 'draft-1')
  })

  it('restores an archived record without changing publication status', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)

    await user.click(await screen.findByRole('button', { name: 'Restore' }))
    await waitFor(() =>
      expect(mocks.updateAdminContent).toHaveBeenCalledWith(session, 'pyq', 'archived-1', { active: true }),
    )
  })

  it('preserves archive state when editing an archived record without a status change', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)

    const archivedRow = (await screen.findByText('Archived paper')).closest('article')
    await user.click(archivedRow!.querySelector('button')!)
    await user.click(await screen.findByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mocks.updateAdminContent).toHaveBeenCalled())
    const body = mocks.updateAdminContent.mock.calls[0][3]
    expect(body).not.toHaveProperty('active')
    expect(body.status).toBe('VERIFIED')
  })

  it('requires an explicit reactivation decision when status changes on an archived record', async () => {
    const user = userEvent.setup()
    mocks.confirm.mockResolvedValue(false)
    render(<AdminContentManager kind="pyq" />)

    const archivedRow = (await screen.findByText('Archived paper')).closest('article')
    await user.click(archivedRow!.querySelector('button')!)
    const editPanel = (await screen.findByText('Edit metadata')).closest('form')!
    await user.selectOptions(within(editPanel).getByLabelText('Publication status'), 'DRAFT')
    await user.click(within(editPanel).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mocks.confirm).toHaveBeenCalled())
    expect(mocks.confirm.mock.calls[0][0]).toMatchObject({ title: 'Restore this archived item?' })
    const body = mocks.updateAdminContent.mock.calls[0][3]
    expect(body.status).toBe('DRAFT')
    expect(body.active).toBe(false)
  })

  it('filters by search, status and archive state and clears filters', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)

    await user.type(await screen.findByPlaceholderText('Title or filename'), 'archived')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Archived paper')).toBeInTheDocument()
    expect(screen.queryByText('Draft paper')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Archive state'), 'active')
    expect(screen.getByText(/No uploaded items match the current search and filters/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(await screen.findByText('Draft paper')).toBeInTheDocument()
    expect(screen.getByText('Archived paper')).toBeInTheDocument()
  })
})
