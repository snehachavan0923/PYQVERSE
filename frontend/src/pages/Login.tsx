import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import type { AuthSession } from '../types/auth'
import { notification } from '../services/notification'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [otpMode, setOtpMode] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const submitting = useRef(false)
  const { setSession } = useAuth()
  const navigate = useNavigate()

  const enterSession = (session: AuthSession) => {
    setSession(session)
    navigate(session.profile.role === 'ADMIN_FACULTY' ? '/admin' : session.profile.onboarding_completed ? '/student' : '/onboarding')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true
    setError('')
    setLoading(true)
    try {
      if (otpMode) {
        await api.post('/auth/send-otp', { email, purpose: 'login' })
        setSent(true)
      } else {
        const response = await api.post<AuthSession>('/auth/login', { email, password })
        enterSession(response.data)
        await notification.toast('Signed in successfully')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Unable to complete sign in')
      await notification.error('Sign-in failed', err.response?.data?.detail ?? 'Unable to complete sign in')
    } finally {
      setLoading(false)
      submitting.current = false
    }
  }

  return (
    <section className="auth-card">
      <div className="brand-mark">PYQ</div>
      <p className="eyebrow">RVCE Academic Portal</p>
      <h1>Welcome back</h1>
      <p className="muted">Sign in to your PYQVERSE workspace.</p>
      {sent ? (
        <button className="secondary-button" onClick={() => navigate('/verify-otp', { state: { email, purpose: 'login' } })}>
          Enter OTP
        </button>
      ) : (
        <form onSubmit={submit}>
          <label>Email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          {!otpMode && (
            <label>Password
              <span className="password-field">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="password-toggle"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  onClick={() => setShowPassword((visible) => !visible)}
                >
                  {showPassword ? (
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10.6 10.6a2 2 0 002.8 2.8M9.9 4.2A11.8 11.8 0 0112 4c5.5 0 9.5 5.5 9.5 8a8.7 8.7 0 01-2.2 3.2M6.2 6.2C4.3 7.5 3 9.3 2.5 12c0 2.5 4 8 9.5 8 1.1 0 2.1-.2 3-.6" /></svg>
                  ) : (
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12S6.5 6.5 12 6.5 21.5 12 21.5 12 17.5 17.5 12 17.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="2.5" /></svg>
                  )}
                </button>
              </span>
            </label>
          )}
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button" disabled={loading}>{otpMode ? 'Send login OTP' : 'Sign in'}</button>
        </form>
      )}
      <button className="text-button" onClick={() => { setOtpMode(!otpMode); setSent(false); setError('') }}>
        {otpMode ? 'Use password instead' : 'Use email OTP instead'}
      </button>
      <p className="muted">New student? <Link to="/register">Create an account</Link></p>
    </section>
  )
}
