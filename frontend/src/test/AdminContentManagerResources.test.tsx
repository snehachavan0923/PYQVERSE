import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mocks = vi.hoisted(() => ({
  listAdminContent: vi.fn(),
  updateAdminContent: vi.fn(),
  archiveAdminContent: vi.fn(),
  deleteAdminContent: vi.fn(),
  uploadAdminContent: vi.fn(),
  listAdminUnits: vi.fn(),
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
  listAdminUnits: mocks.listAdminUnits,
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

const fileResource = {
  id: 'res-file-1',
  subject_id: 'sub-1',
  subject_code: 'CS201',
  subject_name: 'Data Structures',
  title: 'Trees and Graphs PDF',
  description: 'Lecture notes on binary trees',
  resource_type: 'NOTES',
  resource_source: 'FILE' as const,
  original_filename: 'trees.pdf',
  file_type: 'pdf',
  file_size: 10240,
  verification_status: 'VERIFIED',
  active: true,
}

const linkResource = {
  id: 'res-link-1',
  subject_id: 'sub-1',
  subject_code: 'CS201',
  subject_name: 'Data Structures',
  title: 'MIT Graph Algorithms Video',
  description: 'Full lecture video on Dijkstra',
  resource_type: 'STUDY_MATERIAL',
  resource_source: 'LINK' as const,
  external_url: 'https://www.youtube.com/watch?v=2E7MmKv0Y24',
  link_title: 'MIT OpenCourseWare Dijkstra',
  original_filename: null,
  file_type: null,
  file_size: null,
  verification_status: 'VERIFIED',
  active: true,
}

const bothResource = {
  id: 'res-both-1',
  subject_id: 'sub-1',
  subject_code: 'CS201',
  subject_name: 'Data Structures',
  title: 'Sorting Algorithms Guide & Slides',
  description: 'Comprehensive guide with video link',
  resource_type: 'NOTES',
  resource_source: 'BOTH' as const,
  external_url: 'https://algs4.cs.princeton.edu/lectures/',
  link_title: 'Princeton Slides',
  original_filename: 'sorting.pdf',
  file_type: 'pdf',
  file_size: 20480,
  unit_number: 2,
  unit_title: 'Sorting and Searching',
  verification_status: 'VERIFIED',
  active: true,
}

describe('AdminContentManager — Learning Resource Sources (FILE, LINK, BOTH)', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.restoreAllMocks()
    Object.values(mocks).forEach((mock) => mock.mockReset())
    mocks.useAuth.mockReturnValue({ session })
    mocks.useAdminSubjects.mockReturnValue([
      { id: 'sub-1', code: 'CS201', name: 'Data Structures', active: true },
    ])
    mocks.listAdminContent.mockResolvedValue({
      items: [fileResource, linkResource, bothResource],
      total: 3,
    })
    mocks.listAdminUnits.mockResolvedValue([
      { id: 'unit-1', title: 'Trees', order_index: 1 },
      { id: 'unit-2', title: 'Sorting and Searching', order_index: 2 },
    ])
    mocks.uploadAdminContent.mockResolvedValue({ id: 'new-res-1' })
  })

  it('renders all three resource types with source badges and proper action buttons', async () => {
    render(<AdminContentManager kind="resource" />)

    await waitFor(() => {
      expect(screen.getByText('Trees and Graphs PDF')).toBeInTheDocument()
      expect(screen.getByText('MIT Graph Algorithms Video')).toBeInTheDocument()
      expect(screen.getByText('Sorting Algorithms Guide & Slides')).toBeInTheDocument()
    })

    // Badges
    expect(screen.getByText('📄 File')).toBeInTheDocument()
    expect(screen.getByText('🔗 Link')).toBeInTheDocument()
    expect(screen.getByText('📄+🔗 File & Link')).toBeInTheDocument()

    // YouTube link has Watch Video button
    const watchVideoBtn = screen.getByRole('link', { name: /watch video/i })
    expect(watchVideoBtn).toHaveAttribute('href', 'https://www.youtube.com/watch?v=2E7MmKv0Y24')
    expect(watchVideoBtn).toHaveAttribute('target', '_blank')
    expect(watchVideoBtn).toHaveAttribute('rel', 'noopener noreferrer')

    // Web link has Open Link button
    const openLinkBtn = screen.getByRole('link', { name: /open link/i })
    expect(openLinkBtn).toHaveAttribute('href', 'https://algs4.cs.princeton.edu/lectures/')

    // Unit tag
    expect(screen.getByText(/Unit 2: Sorting and Searching/)).toBeInTheDocument()
  })

  it('switches between File, Link, and Both in upload modal and displays live YouTube preview', async () => {
    render(<AdminContentManager kind="resource" />)
    const user = userEvent.setup()

    const uploadBtn = await screen.findByRole('button', { name: 'Upload Document' })
    await user.click(uploadBtn)
    await screen.findByRole('dialog')

    // Source buttons should be present
    const fileSourceBtn = screen.getByRole('radio', { name: 'File Upload' })
    const linkSourceBtn = screen.getByRole('radio', { name: 'External Link' })
    const bothSourceBtn = screen.getByRole('radio', { name: 'Both' })

    expect(fileSourceBtn).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByLabelText(/^file$/i)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/https:\/\/www\.youtube/i)).not.toBeInTheDocument()

    // Switch to External Link
    await user.click(linkSourceBtn)
    expect(linkSourceBtn).toHaveAttribute('aria-checked', 'true')
    expect(screen.queryByLabelText(/^file$/i)).not.toBeInTheDocument()

    const urlInput = screen.getByPlaceholderText(/https:\/\/www\.youtube/i)
    expect(urlInput).toBeInTheDocument()

    // Type YouTube URL and verify live preview appears
    fireEvent.change(urlInput, { target: { value: 'https://youtu.be/dQw4w9WgXcQ' } })

    await waitFor(() => {
      expect(screen.getByText('▶ YouTube Video')).toBeInTheDocument()
      expect(screen.getByText(/Video ID: dQw4w9WgXcQ/i)).toBeInTheDocument()
      expect(screen.getByAltText('YouTube thumbnail')).toHaveAttribute(
        'src',
        'https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg',
      )
    })

    // Switch to Both
    await user.click(bothSourceBtn)
    expect(bothSourceBtn).toHaveAttribute('aria-checked', 'true')
    // Both file and URL input should be visible
    expect(screen.getByLabelText(/^file$/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/https:\/\/www\.youtube/i)).toBeInTheDocument()
  })

  it('validates URL when External Link source is selected', async () => {
    render(<AdminContentManager kind="resource" />)
    const user = userEvent.setup()

    const uploadBtn = await screen.findByRole('button', { name: 'Upload Document' })
    await user.click(uploadBtn)
    await screen.findByRole('dialog')

    // Switch to External Link
    await user.click(screen.getByRole('radio', { name: 'External Link' }))

    // Fill title but leave URL empty
    const titleInput = screen.getByLabelText(/title \(required\)/i)
    await user.type(titleInput, 'Awesome Course')

    // Click submit
    const submitBtn = screen.getByRole('button', { name: /^upload$/i })
    await user.click(submitBtn)

    expect(screen.getByText('Enter a valid resource URL.')).toBeInTheDocument()

    // Fill invalid URL
    const urlInput = screen.getByPlaceholderText(/https:\/\/www\.youtube/i)
    fireEvent.change(urlInput, { target: { value: 'not-a-valid-url' } })

    await user.click(submitBtn)
    expect(
      screen.getByText('Please enter a valid HTTP or HTTPS URL (e.g. https://...).'),
    ).toBeInTheDocument()
  })
})
