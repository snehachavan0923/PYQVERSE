import { Outlet } from 'react-router-dom'
import ThemeToggle from '../components/ThemeToggle'

const CURRENT_YEAR = new Date().getFullYear()

export default function MainLayout() {
  return (
    <div className="app-shell">
      <ThemeToggle />
      <main className="app-main">
        <Outlet />
      </main>
      <footer className="app-footer">
        PYQVERSE &copy; {CURRENT_YEAR}
      </footer>
    </div>
  )
}
