import { Outlet } from 'react-router-dom'
import ThemeToggle from '../components/ThemeToggle'

const CURRENT_YEAR = new Date().getFullYear()

function BrandMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H12v16H6.5A2.5 2.5 0 0 1 4 17.5v-11Z" />
      <path d="M20 6.5A2.5 2.5 0 0 0 17.5 4H12v16h5.5a2.5 2.5 0 0 0 2.5-2.5v-11Z" />
      <path d="M12 8v8" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m5 12 4.5 4.5L19 7" />
    </svg>
  )
}

const FEATURES = [
  'Published question papers for your enrolled subjects.',
  'Syllabus documents and faculty-verified learning resources.',
  'Secure previews and downloads with role-based access.',
]

export default function MainLayout() {
  return (
    <div className="app-shell">
      <ThemeToggle />
      <main className="app-main">
        <div className="auth-shell">
          <aside className="auth-aside" aria-hidden="true">
            <div className="auth-brand">
              <span className="brand-badge">
                <BrandMark />
              </span>
              PYQVERSE
            </div>
            <div className="auth-aside-copy">
              <p className="eyebrow">Academic workspace</p>
              <h2>Every paper, every semester, organised in one place.</h2>
              <p>
                A focused preparation workspace for RVCE students — built around your real
                syllabus, question papers and learning resources.
              </p>
            </div>
            <ul className="auth-feature-list">
              {FEATURES.map((feature) => (
                <li key={feature}>
                  <span className="auth-feature-icon">
                    <CheckIcon />
                  </span>
                  {feature}
                </li>
              ))}
            </ul>
            <span className="auth-aside-foot">RVCE academic preparation workspace</span>
          </aside>
          <div className="auth-content">
            <Outlet />
          </div>
        </div>
      </main>
      <footer className="app-footer">
        PYQVERSE &copy; {CURRENT_YEAR}
      </footer>
    </div>
  )
}
