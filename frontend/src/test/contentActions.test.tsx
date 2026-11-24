import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mocks = vi.hoisted(() => ({
  listStudentPyqs: vi.fn(),
  openStudentDownload: vi.fn(),
  openStudentPreview: vi.fn(),
  triggerDownload: vi.fn(),
  error: vi.fn(),
  retryError: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ session: { access_token: 'token' } }),
}))

vi.mock('../hooks/useStudentSubjects', () => ({
  useStudentSubjects: () => [],
}))

vi.mock('../services/contentApi', () => ({
  listStudentPyqs: mocks.listStudentPyqs,
  openStudentDownload: mocks.openStudentDownload,
  openStudentPreview: mocks.openStudentPreview,
}))

vi.mock('../services/notification', () => ({
  default: {
    error: mocks.error,
    retryError: mocks.retryError,
  },
}))

vi.mock('../utils/documentActions', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/documentActions')>()
  return { ...actual, triggerDownload: mocks.triggerDownload }
})

import ContentActions from '../components/ContentActions'
import StudentPyqs from '../pages/StudentPyqs'

const paper = {
  id: 'paper-1',
  subject_id: 'subject-1',
  subject_code: 'CS233AI',
  subject_name: 'Data Structures',
  original_filename: 'SEE-2025.pdf',
  file_type: 'pdf',
  title: 'SEE 2025',
  description: null,
  exam_type: 'SEE',
  cie_number: null,
  examination_year: 2025,
  verification_status: 'VERIFIED',
  active: true,
}

function fakeWindow() {
  return {
    location: { href: '' },
    opener: {},
    close: vi.fn(),
  } as unknown as Window & { close: ReturnType<typeof vi.fn> }
}

beforeEach(() => {
  vi.restoreAllMocks()
  Object.values(mocks).forEach((mock) => mock.mockReset())
  mocks.listStudentPyqs.mockResolvedValue({ items: [paper], total: 1 })
  mocks.openStudentPreview.mockResolvedValue('https://signed.example/preview')
  mocks.openStudentDownload.mockResolvedValue('https://signed.example/download')
  mocks.retryError.mockResolvedValue(false)
})

describe('ContentActions', () => {
  it('renders accessible view and download icon controls', () => {
    render(<ContentActions label="Syllabus" onView={vi.fn()} onDownload={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'View PDF Syllabus' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Download Syllabus' })).toBeEnabled()
  })

  it('disables both actions while busy and blocks view for unsupported files', () => {
    render(
      <ContentActions
        label="Notes"
        busy
        viewDisabled
        onView={vi.fn()}
        onDownload={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'View PDF Notes' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Download Notes' })).toBeDisabled()
  })
})

describe('StudentPyqs document actions', () => {
  it('opens the PDF preview in a new tab', async () => {
    const user = userEvent.setup()
    const win = fakeWindow()
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(win)

    render(<StudentPyqs />)
    await user.click(await screen.findByRole('button', { name: 'View PDF SEE 2025' }))

    await waitFor(() =>
      expect(mocks.openStudentPreview).toHaveBeenCalledWith(
        expect.objectContaining({ access_token: 'token' }),
        'pyq',
        'paper-1',
      ),
    )
    expect(openSpy).toHaveBeenCalledWith('', '_blank')
    expect(win.location.href).toBe('https://signed.example/preview')
  })

  it('downloads without opening a new tab', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open')

    render(<StudentPyqs />)
    await user.click(await screen.findByRole('button', { name: 'Download SEE 2025' }))

    await waitFor(() =>
      expect(mocks.openStudentDownload).toHaveBeenCalledWith(
        expect.objectContaining({ access_token: 'token' }),
        'pyq',
        'paper-1',
      ),
    )
    expect(mocks.triggerDownload).toHaveBeenCalledWith('https://signed.example/download')
    expect(openSpy).not.toHaveBeenCalled()
  })

  it('closes the preview tab and offers a retry when the link cannot be created', async () => {
    const user = userEvent.setup()
    const win = fakeWindow()
    vi.spyOn(window, 'open').mockReturnValue(win)
    mocks.openStudentPreview.mockRejectedValueOnce(new Error('expired'))
    mocks.retryError.mockResolvedValue(false)

    render(<StudentPyqs />)
    await user.click(await screen.findByRole('button', { name: 'View PDF SEE 2025' }))

    await waitFor(() => expect(mocks.retryError).toHaveBeenCalled())
    expect(win.close).toHaveBeenCalled()
  })
})
