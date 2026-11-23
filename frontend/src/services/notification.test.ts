import '@testing-library/jest-dom/vitest'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { fire } = vi.hoisted(() => ({
  fire: vi.fn(() => Promise.resolve({ isConfirmed: true })),
}))

vi.mock('sweetalert2', () => ({
  default: { fire },
}))

import { notification } from './notification'

describe('PYQVERSE SweetAlert2 notifications', () => {
  beforeEach(() => {
    fire.mockClear()
  })

  it('uses the light theme styling', async () => {
    document.documentElement.dataset.theme = 'light'
    await notification.success('Saved')
    expect(fire).toHaveBeenCalledWith(expect.objectContaining({
      background: '#ffffff',
      color: '#17212b',
      icon: 'success',
    }))
  })

  it('uses the dark theme styling', async () => {
    document.documentElement.dataset.theme = 'dark'
    await notification.error('Failed')
    expect(fire).toHaveBeenCalledWith(expect.objectContaining({
      background: '#132120',
      color: '#edf7f4',
      icon: 'error',
    }))
  })

  it('renders toasts for simple success messages', async () => {
    await notification.toast('Signed in')
    expect(fire).toHaveBeenCalledWith(expect.objectContaining({
      toast: true,
      position: 'top-end',
      showConfirmButton: false,
    }))
  })
})
