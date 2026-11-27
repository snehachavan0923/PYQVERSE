import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  listStudentResources: vi.fn(),
  openStudentPreview: vi.fn(),
  openStudentDownload: vi.fn(),
  useAuth: vi.fn(),
  useStudentSubjects: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: mocks.useAuth,
}))

vi.mock('../hooks/useStudentSubjects', () => ({
  useStudentSubjects: mocks.useStudentSubjects,
}))

vi.mock('../services/contentApi', () => ({
  listStudentResources: mocks.listStudentResources,
  openStudentPreview: mocks.openStudentPreview,
  openStudentDownload: mocks.openStudentDownload,
}))

vi.mock('../services/notification', () => ({
  default: {
    toast: vi.fn(),
    error: vi.fn(),
    retryError: vi.fn(),
  },
}))

import StudentResources from '../pages/StudentResources'

const session = { access_token: 'student-token' }

const sampleResources = [
  {
    id: 'res-1',
    subject_id: 'sub-1',
    subject_code: 'CS201',
    subject_name: 'Data Structures',
    title: 'Trees Study Notes PDF',
    description: 'Binary search tree fundamentals',
    resource_type: 'NOTES',
    resource_source: 'FILE' as const,
    original_filename: 'trees.pdf',
    file_type: 'pdf',
    file_size: 15360,
    verification_status: 'VERIFIED',
    active: true,
  },
  {
    id: 'res-2',
    subject_id: 'sub-1',
    subject_code: 'CS201',
    subject_name: 'Data Structures',
    title: 'MIT Graph Algorithms Video',
    description: 'Dijkstra and BFS video explanations',
    resource_type: 'STUDY_MATERIAL',
    resource_source: 'LINK' as const,
    external_url: 'https://www.youtube.com/watch?v=2E7MmKv0Y24',
    link_title: 'MIT OCW Dijkstra Lecture',
    original_filename: null,
    file_type: null,
    file_size: null,
    verification_status: 'VERIFIED',
    active: true,
  },
  {
    id: 'res-3',
    subject_id: 'sub-1',
    subject_code: 'CS201',
    subject_name: 'Data Structures',
    title: 'Sorting Algorithms Cheat Sheet & Guide',
    description: 'Quick reference sheet with slides link',
    resource_type: 'REFERENCE',
    resource_source: 'BOTH' as const,
    external_url: 'https://algs4.cs.princeton.edu/lectures/',
    link_title: 'Princeton Slides',
    original_filename: 'sorting.pdf',
    file_type: 'pdf',
    file_size: 30720,
    unit_number: 1,
    unit_title: 'Sorting Algorithms',
    verification_status: 'VERIFIED',
    active: true,
  },
]

describe('StudentResources — Learning Resources Viewing & Source Filtering', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.restoreAllMocks()
    Object.values(mocks).forEach((mock) => mock.mockReset())
    mocks.useAuth.mockReturnValue({ session })
    mocks.useStudentSubjects.mockReturnValue([
      { id: 'sub-1', code: 'CS201', name: 'Data Structures' },
    ])
    mocks.listStudentResources.mockResolvedValue({ items: sampleResources, total: 3 })
  })

  it('renders student resources with source badges, video thumbnail, and actions', async () => {
    render(<StudentResources />)

    await waitFor(() => {
      expect(screen.getByText('Trees Study Notes PDF')).toBeInTheDocument()
      expect(screen.getByText('MIT Graph Algorithms Video')).toBeInTheDocument()
      expect(screen.getByText('Sorting Algorithms Cheat Sheet & Guide')).toBeInTheDocument()
    })

    // Badges
    expect(screen.getByText('📄 File')).toBeInTheDocument()
    expect(screen.getByText('🔗 Link')).toBeInTheDocument()
    expect(screen.getByText('📄+🔗 File & Link')).toBeInTheDocument()

    // Video thumbnail image
    const thumb = screen.getByAltText('Video thumbnail')
    expect(thumb).toHaveAttribute('src', 'https://img.youtube.com/vi/2E7MmKv0Y24/hqdefault.jpg')

    // Watch video button
    const watchBtn = screen.getByRole('link', { name: /watch video/i })
    expect(watchBtn).toHaveAttribute('href', 'https://www.youtube.com/watch?v=2E7MmKv0Y24')
    expect(watchBtn).toHaveAttribute('target', '_blank')
    expect(watchBtn).toHaveAttribute('rel', 'noopener noreferrer')

    // Open Resource button for BOTH
    const openBtn = screen.getByRole('link', { name: /open resource/i })
    expect(openBtn).toHaveAttribute('href', 'https://algs4.cs.princeton.edu/lectures/')

    // Unit tag
    expect(screen.getByText('Unit 1: Sorting Algorithms')).toBeInTheDocument()
  })

  it('filters by source (Files only, External links only, Both)', async () => {
    render(<StudentResources />)

    await waitFor(() => {
      expect(screen.getByText('Trees Study Notes PDF')).toBeInTheDocument()
    })

    const sourceSelect = screen.getByLabelText(/^source$/i)

    // Filter to External links only
    fireEvent.change(sourceSelect, { target: { value: 'LINK' } })

    expect(screen.queryByText('Trees Study Notes PDF')).not.toBeInTheDocument()
    expect(screen.getByText('MIT Graph Algorithms Video')).toBeInTheDocument()
    expect(screen.queryByText('Sorting Algorithms Cheat Sheet & Guide')).not.toBeInTheDocument()

    // Filter to Files only
    fireEvent.change(sourceSelect, { target: { value: 'FILE' } })

    expect(screen.getByText('Trees Study Notes PDF')).toBeInTheDocument()
    expect(screen.queryByText('MIT Graph Algorithms Video')).not.toBeInTheDocument()
    expect(screen.queryByText('Sorting Algorithms Cheat Sheet & Guide')).not.toBeInTheDocument()

    // Filter to Both
    fireEvent.change(sourceSelect, { target: { value: 'BOTH' } })

    expect(screen.queryByText('Trees Study Notes PDF')).not.toBeInTheDocument()
    expect(screen.queryByText('MIT Graph Algorithms Video')).not.toBeInTheDocument()
    expect(screen.getByText('Sorting Algorithms Cheat Sheet & Guide')).toBeInTheDocument()
  })
})
