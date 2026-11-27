import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mocks = vi.hoisted(() => ({
  listAdminContent: vi.fn(),
  updateAdminContent: vi.fn(),
  archiveAdminContent: vi.fn(),
  deleteAdminContent: vi.fn(),
  uploadAdminContent: vi.fn(),
  openAdminPreview: vi.fn(),
  openAdminDownload: vi.fn(),
  confirm: vi.fn(),
  toast: vi.fn(),
  error: vi.fn(),
  retryError: vi.fn(),
  useAuth: vi.fn(),
  useAdminSubjects: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: mocks.useAuth,
}))

vi.mock('../hooks/useAdminSubjects', () => ({
  useAdminSubjects: mocks.useAdminSubjects,
}))

vi.mock('../services/contentApi', () => ({
  listAdminContent: mocks.listAdminContent,
  updateAdminContent: mocks.updateAdminContent,
  archiveAdminContent: mocks.archiveAdminContent,
  deleteAdminContent: mocks.deleteAdminContent,
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
  mocks.deleteAdminContent.mockResolvedValue({ message: 'deleted' })
  mocks.uploadAdminContent.mockResolvedValue({})
  mocks.confirm.mockResolvedValue(true)
  mocks.retryError.mockResolvedValue(false)
  mocks.useAuth.mockReturnValue({ session: { access_token: 'token' } })
  mocks.useAdminSubjects.mockReturnValue([
    { id: 'subject-1', code: 'CS233AI', name: 'Data Structures', active: true },
  ])
})

async function openUploadDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Upload Document' }))
  return await screen.findByRole('dialog')
}

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

  it('sends one upload request for repeated form submissions while pending', async () => {
    const user = userEvent.setup()
    let resolveUpload!: (value: unknown) => void
    mocks.uploadAdminContent.mockReturnValue(
      new Promise((resolve) => {
        resolveUpload = resolve
      }),
    )
    render(<AdminContentManager kind="pyq" />)
    await screen.findByText('Draft paper')
    const listCallsBeforeUpload = mocks.listAdminContent.mock.calls.length

    const dialog = await openUploadDialog(user)
    const file = new File(['pdf bytes'], 'paper.pdf', { type: 'application/pdf' })
    await user.upload(within(dialog).getByLabelText('File'), file)
    await waitFor(() => expect(within(dialog).getByLabelText('Subject')).toHaveValue('subject-1'))
    const form = dialog.querySelector('form')!

    act(() => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    expect(mocks.uploadAdminContent).toHaveBeenCalledTimes(1)
    expect(within(dialog).getByRole('button', { name: 'Uploading…' })).toBeDisabled()
    resolveUpload({})
    await waitFor(() =>
      expect(mocks.listAdminContent).toHaveBeenCalledTimes(listCallsBeforeUpload + 1),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('shows duplicate errors inside the modal and preserves upload fields after failure', async () => {
    const user = userEvent.setup()
    mocks.uploadAdminContent.mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: 'An active question paper with identical PDF content already exists' },
      },
    })
    render(<AdminContentManager kind="pyq" />)

    const dialog = await openUploadDialog(user)
    const file = new File(['pdf bytes'], 'paper.pdf', { type: 'application/pdf' })
    await user.upload(within(dialog).getByLabelText('File'), file)
    await user.type(within(dialog).getByLabelText('Title (optional)'), 'Exam paper title')
    fireEvent.submit(dialog.querySelector('form')!)

    await waitFor(() =>
      expect(within(dialog).getByRole('alert')).toHaveTextContent(
        'An active question paper with identical PDF content already exists',
      ),
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('File')).toHaveProperty('files.0.name', 'paper.pdf')
    expect(within(dialog).getByLabelText('Title (optional)')).toHaveValue('Exam paper title')
  })

  it('offers an upload action in the empty state when there are no documents', async () => {
    mocks.listAdminContent.mockResolvedValue({ items: [], total: 0 })
    render(<AdminContentManager kind="syllabus" />)

    expect(await screen.findByText('No content found')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Upload Document' })).toHaveLength(2)
  })

  it('opens the syllabus modal with syllabus-specific fields', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="syllabus" />)

    const dialog = await openUploadDialog(user)
    expect(within(dialog).getByRole('heading', { name: 'Upload Syllabus Document' })).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Version')).toBeInTheDocument()
    expect(screen.queryByLabelText('Exam type')).not.toBeInTheDocument()
  })

  it('shows inline validation errors from the footer action without calling the upload API', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)

    const dialog = await openUploadDialog(user)
    await user.click(within(dialog).getByRole('button', { name: 'Upload' }))

    expect(within(dialog).getByRole('alert')).toHaveTextContent('Select a file to upload.')
    expect(mocks.uploadAdminContent).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('closes on Escape when idle but not while an upload is pending', async () => {
    const user = userEvent.setup()
    let resolveUpload!: (value: unknown) => void
    mocks.uploadAdminContent.mockReturnValue(
      new Promise((resolve) => {
        resolveUpload = resolve
      }),
    )
    render(<AdminContentManager kind="pyq" />)
    await screen.findByText('Draft paper')

    let dialog = await openUploadDialog(user)
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    dialog = await openUploadDialog(user)
    await user.upload(within(dialog).getByLabelText('File'), new File(['pdf'], 'paper.pdf', { type: 'application/pdf' }))
    fireEvent.submit(dialog.querySelector('form')!)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Close dialog' })).toBeDisabled()

    resolveUpload({})
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('closes on backdrop click and resets the form for the next upload', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)
    await screen.findByText('Draft paper')

    let dialog = await openUploadDialog(user)
    await user.type(within(dialog).getByLabelText('Title (optional)'), 'Discarded title')
    fireEvent.mouseDown(document.querySelector('.document-modal-backdrop')!)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    dialog = await openUploadDialog(user)
    expect(within(dialog).getByLabelText('Title (optional)')).toHaveValue('')
    expect(within(dialog).getByLabelText('File')).toHaveValue('')
  })

  it('renders a delete button for content items', async () => {
    render(<AdminContentManager kind="pyq" />)
    await screen.findByText('Draft paper')

    const deleteButtons = screen.getAllByRole('button', { name: /Delete/ })
    expect(deleteButtons.length).toBeGreaterThanOrEqual(1)
  })

  it('cancels deletion when Cancel button is clicked in confirmation dialog', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)
    await screen.findByText('Draft paper')

    const deleteBtn = screen.getByRole('button', { name: 'Delete Draft paper' })
    await user.click(deleteBtn)

    const modal = await screen.findByRole('dialog')
    expect(within(modal).getByText('Confirm Permanent Deletion')).toBeInTheDocument()
    expect(within(modal).getByText('Draft paper')).toBeInTheDocument()
    expect(within(modal).getByText(/Previous Year Question Paper/)).toBeInTheDocument()
    expect(within(modal).getByText(/Warning:/)).toBeInTheDocument()

    const cancelBtn = within(modal).getByRole('button', { name: 'Cancel' })
    await user.click(cancelBtn)

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(mocks.deleteAdminContent).not.toHaveBeenCalled()
    expect(screen.getByText('Draft paper')).toBeInTheDocument()
  })

  it('deletes content item when Confirm Delete is clicked', async () => {
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)
    await screen.findByText('Draft paper')

    const deleteBtn = screen.getByRole('button', { name: 'Delete Draft paper' })
    await user.click(deleteBtn)

    const modal = await screen.findByRole('dialog')
    const confirmBtn = within(modal).getByRole('button', { name: 'Confirm Delete' })
    await user.click(confirmBtn)

    await waitFor(() => {
      expect(mocks.deleteAdminContent).toHaveBeenCalledWith(session, 'pyq', 'draft-1')
      expect(mocks.toast).toHaveBeenCalledWith('success', 'Content deleted successfully')
    })
    await waitFor(() => {
      expect(screen.queryByText('Draft paper')).not.toBeInTheDocument()
    })
  })

  it('shows error notification when deleteAdminContent rejects', async () => {
    mocks.deleteAdminContent.mockRejectedValueOnce({
      response: { data: { detail: 'Cannot delete question paper: extracted questions depend on it.' } },
    })
    const user = userEvent.setup()
    render(<AdminContentManager kind="pyq" />)
    await screen.findByText('Draft paper')

    const deleteBtn = screen.getByRole('button', { name: 'Delete Draft paper' })
    await user.click(deleteBtn)

    const modal = await screen.findByRole('dialog')
    const confirmBtn = within(modal).getByRole('button', { name: 'Confirm Delete' })
    await user.click(confirmBtn)

    await waitFor(() => {
      expect(mocks.error).toHaveBeenCalledWith(
        'Deletion failed',
        'Cannot delete question paper: extracted questions depend on it.',
      )
    })
  })
})
