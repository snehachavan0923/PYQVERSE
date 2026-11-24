import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ThemeToggle from '../components/ThemeToggle'
import { currentTheme } from '../services/notification'

function stubMatchMedia(matches = false) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

beforeEach(() => {
  localStorage.clear()
  delete document.documentElement.dataset.theme
  stubMatchMedia(false)
})

describe('ThemeToggle', () => {
  it('applies the light theme by default and toggles to dark', async () => {
    const user = userEvent.setup()
    render(<ThemeToggle />)

    expect(document.documentElement.dataset.theme).toBe('light')
    await user.click(screen.getByRole('button', { name: 'Switch to dark theme' }))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('pyqverse_theme')).toBe('dark')
  })

  it('restores a stored dark preference', () => {
    localStorage.setItem('pyqverse_theme', 'dark')
    render(<ThemeToggle />)

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
  })
})

describe('notification theme resolution', () => {
  it('uses the active document theme for SweetAlert2 dialogs', () => {
    document.documentElement.dataset.theme = 'dark'
    expect(currentTheme()).toBe('dark')

    document.documentElement.dataset.theme = 'light'
    expect(currentTheme()).toBe('light')
  })

  it('falls back to the stored preference when the attribute is absent', () => {
    localStorage.setItem('pyqverse_theme', 'dark')
    expect(currentTheme()).toBe('dark')
  })
})
