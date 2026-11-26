import { useLayoutEffect, useState } from 'react'

type Theme = 'light' | 'dark'

function initialTheme(): Theme {
  const stored = localStorage.getItem('pyqverse_theme')
  if (stored === 'light' || stored === 'dark') return stored
  return 'dark'
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7Z" />
    </svg>
  )
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('pyqverse_theme', theme)
  }, [theme])

  const next = theme === 'light' ? 'dark' : 'light'

  return (
    <button
      className="theme-toggle"
      type="button"
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      onClick={() => setTheme(next)}
    >
      {theme === 'light' ? <MoonIcon /> : <SunIcon />}
    </button>
  )
}
