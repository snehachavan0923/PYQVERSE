import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import type { AuthSession } from '../types/auth'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [otpMode, setOtpMode] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)
  const [loading, setLoading] = useState(false)
  const { setSession } = useAuth()
  const navigate = useNavigate()

  const enterSession = (session: AuthSession) => {
    setSession(session)
    navigate(session.profile.role === 'ADMIN_FACULTY' ? '/admin' : session.profile.onboarding_completed ? '/student' : '/onboarding')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (otpMode) {
        await api.post('/auth/send-otp', { email, purpose: 'login' })
        setSent(true)
      } else {
        const response = await api.post<AuthSession>('/auth/login', { email, password })
        enterSession(response.data)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Unable to complete sign in')
    } finally {
      setLoading(false)
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
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
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
