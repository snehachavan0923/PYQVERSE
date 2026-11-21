import { Outlet } from 'react-router-dom'

const CURRENT_YEAR = new Date().getFullYear()

export default function MainLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <main className="flex flex-1 items-center justify-center px-6">
        <Outlet />
      </main>
      <footer className="border-t border-slate-800 py-4 text-center text-sm text-slate-500">
        PYQVERSE &copy; {CURRENT_YEAR}
      </footer>
    </div>
  )
}
