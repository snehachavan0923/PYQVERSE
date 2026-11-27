import { useEffect, useState } from 'react'
import ThemeToggle from '../components/ThemeToggle'
import './Home.css'

const CURRENT_YEAR = new Date().getFullYear()

function BrandMark() {
  return (
    <svg className="home-brand-mark" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H12v16H6.5A2.5 2.5 0 0 1 4 17.5v-11Z" />
      <path d="M20 6.5A2.5 2.5 0 0 0 17.5 4H12v16h5.5a2.5 2.5 0 0 0 2.5-2.5v-11Z" />
      <path d="M12 8v8" />
    </svg>
  )
}

function FeatureIcon({ kind }: { kind: string }) {
  if (kind === 'intel') {
    return (
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="m7 14 4-4 3 3 5-7" />
      </svg>
    )
  }
  if (kind === 'topic') {
    return (
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 3h10l4 4v14H5z" />
      <path d="M15 3v5h4" />
    </svg>
  )
}

export default function Home() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileOpen(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const closeMobile = () => setMobileOpen(false)

  return (
    <div className="home-page">
      <nav className={`home-nav${scrolled ? ' scrolled' : ''}`}>
        <a href="/" className="home-brand" onClick={closeMobile}>
          <BrandMark />
          <span>PYQVERSE</span>
        </a>

        <div className="home-nav-links">
          <a href="#hero">Home</a>
          <a href="#features">Features</a>
          <a href="#about">About</a>
        </div>

        <div className="home-nav-actions">
          <ThemeToggle />
          <a href="/login" className="home-btn home-btn-secondary home-nav-btn">Login</a>
          <a href="/register" className="home-btn home-btn-primary home-nav-btn">Get Started</a>
          <button
            type="button"
            className="home-mobile-toggle"
            aria-label={mobileOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((v) => !v)}
          >
            {mobileOpen ? (
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </nav>

      {mobileOpen && (
        <div className="home-mobile-menu" role="dialog" aria-label="Mobile Navigation">
          <div className="home-mobile-nav-links">
            <a href="#hero" onClick={closeMobile}>Home</a>
            <a href="#features" onClick={closeMobile}>Features</a>
            <a href="#about" onClick={closeMobile}>About</a>
          </div>
          <div className="home-mobile-nav-actions">
            <a href="/login" className="home-btn home-btn-secondary" onClick={closeMobile}>Login</a>
            <a href="/register" className="home-btn home-btn-primary" onClick={closeMobile}>Get Started</a>
          </div>
        </div>
      )}

      <section id="hero" className="home-hero">
        <div className="home-hero-overlay" />

        {/* Ambient background glow accents (visible in dark mode, hidden in light mode) */}
        <div className="home-hero-glow glow-1" aria-hidden="true" />
        <div className="home-hero-glow glow-2" aria-hidden="true" />

        <div className="home-hero-inner">
          <span className="home-eyebrow">PYQVERSE</span>
          <h1>Prepare smarter. Understand what matters.</h1>
          <p className="lead">
            Your academic preparation, powered by insights from previous-year question papers.
          </p>
          <div className="home-hero-ctas">
            <a href="/register" className="home-btn home-btn-primary">Get Started</a>
            <a href="#features" className="home-btn home-btn-secondary">Explore Features</a>
          </div>

        </div>
      </section>

      <section id="features" className="home-section">
        <h2 className="home-section-title">Built for focused preparation</h2>
        <p className="home-section-sub">Three essentials, nothing more.</p>
        <div className="home-features">
          <article className="home-feature-card">
            <div className="home-feature-icon"><FeatureIcon kind="intel" /></div>
            <h3>PYQ Intelligence</h3>
            <p>Understand historical examination patterns.</p>
          </article>
          <article className="home-feature-card">
            <div className="home-feature-icon"><FeatureIcon kind="topic" /></div>
            <h3>Topic Insights</h3>
            <p>Discover topics that frequently appear in previous papers.</p>
          </article>
          <article className="home-feature-card">
            <div className="home-feature-icon"><FeatureIcon kind="track" /></div>
            <h3>Track Progress</h3>
            <p>Organize bookmarks and monitor your preparation.</p>
          </article>
        </div>
      </section>

      <section id="about" className="home-section">
        <h2 className="home-section-title">How it works</h2>
        <p className="home-section-sub">A simple path from paper to strategy.</p>
        <div className="home-steps">
          <div className="home-step">
            <div className="home-step-num">01</div>
            <h3>Access previous-year papers</h3>
            <p>Browse question papers for your enrolled subjects.</p>
          </div>
          <div className="home-step">
            <div className="home-step-num">02</div>
            <h3>Explore topic insights</h3>
            <p>See which topics recur across years.</p>
          </div>
          <div className="home-step">
            <div className="home-step-num">03</div>
            <h3>Prepare strategically</h3>
            <p>Focus your effort where it matters most.</p>
          </div>
        </div>
      </section>

      <section className="home-cta">
        <div className="home-cta-inner">
          <h2 className="home-section-title">Start preparing with clarity</h2>
          <p className="home-section-sub">Join PYQVERSE and turn past papers into a plan.</p>
          <a href="/register" className="home-btn home-btn-primary">Get Started</a>
        </div>
      </section>

      <footer className="home-footer">
        <div className="home-brand">
          <BrandMark />
          <span>PYQVERSE</span>
        </div>
        <div className="home-footer-copy">© {CURRENT_YEAR} PYQVERSE. All rights reserved.</div>
        <div className="home-footer-links">
          <a href="#features">Features</a>
          <a href="#about">About</a>
          <a href="/login">Login</a>
        </div>
      </footer>
    </div>
  )
}
