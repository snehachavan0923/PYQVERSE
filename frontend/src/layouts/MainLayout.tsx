import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'

const CURRENT_YEAR = new Date().getFullYear()

export default function MainLayout() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => (
    localStorage.getItem('pyqverse_theme') as 'light' | 'dark'
  ) || 'light')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('pyqverse_theme', theme)
  }, [theme])

  return (
    <div className="app-shell">
      <button
        className="theme-toggle"
        type="button"
        aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
        onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
      >
        {theme === 'light' ? 'Moon' : 'Sun'}
      </button>
      <main className="app-main">
        <Outlet />
      </main>
      <footer className="border-t border-slate-800 py-4 text-center text-sm text-slate-500">
        PYQVERSE &copy; {CURRENT_YEAR}
      </footer>
    </div>
  )
}
