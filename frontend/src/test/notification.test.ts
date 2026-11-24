import { beforeEach, describe, expect, it, vi } from 'vitest'

const swalFire = vi.hoisted(() => vi.fn().mockResolvedValue({ isConfirmed: false }))

vi.mock('sweetalert2', () => ({
  default: {
    mixin: () => ({ fire: swalFire }),
    fire: swalFire,
    stopTimer: vi.fn(),
    resumeTimer: vi.fn(),
  },
}))

import { confirm, toast } from '../services/notification'

beforeEach(() => {
  swalFire.mockClear()
  delete document.documentElement.dataset.theme
})

describe('SweetAlert2 theme integration', () => {
  it('applies the active dark theme classes to toasts', async () => {
    document.documentElement.dataset.theme = 'dark'
    await toast('success', 'Saved')

    expect(swalFire).toHaveBeenCalledWith(
      expect.objectContaining({
        customClass: expect.objectContaining({
          popup: expect.stringContaining('pyq-swal-dark'),
        }),
      }),
    )
  })

  it('applies the active light theme classes to toasts', async () => {
    document.documentElement.dataset.theme = 'light'
    await toast('success', 'Saved')

    expect(swalFire).toHaveBeenCalledWith(
      expect.objectContaining({
        customClass: expect.objectContaining({
          popup: expect.stringContaining('pyq-swal-light'),
        }),
      }),
    )
  })

  it('returns a boolean from confirmation dialogs', async () => {
    swalFire.mockResolvedValueOnce({ isConfirmed: true })
    await expect(confirm({ title: 'Archive?' })).resolves.toBe(true)

    swalFire.mockResolvedValueOnce({ isConfirmed: false })
    await expect(confirm({ title: 'Archive?' })).resolves.toBe(false)
  })
})
