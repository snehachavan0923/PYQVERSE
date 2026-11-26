import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { friendlyError } from '../services/errors'
import notifications from '../services/notification'
import { useAuth } from '../context/AuthContext'
import PasswordField from '../components/PasswordField'
import type { AuthSession } from '../types/auth'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const { setSession } = useAuth()
  const navigate = useNavigate()

  const enterSession = (session: AuthSession) => {
    setSession(session)
    void notifications.toast('success', `Welcome back, ${session.user.email}`)
    navigate(
      session.profile.role === 'ADMIN_FACULTY'
        ? '/admin'
        : session.profile.onboarding_completed
          ? '/student'
          : '/onboarding',
      { replace: true },
    )
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true
    setError('')
    setLoading(true)
    try {
      const response = await api.post<AuthSession>(
        '/auth/login',
        { email, password },
        { timeout: 20_000 },
      )
      enterSession(response.data)
    } catch (err) {
      const message = friendlyError(err, 'Unable to sign in')
      setError(message)
      void notifications.error('Sign-in failed', message)
    } finally {
      submitting.current = false
      setLoading(false)
    }
  }

  return (
    <section className="auth-card">
      <div className="brand-mark">PYQ</div>
      <p className="eyebrow">RVCE Academic Portal</p>
      <h1>Welcome back</h1>
      <p className="muted">Sign in to your PYQVERSE workspace with your email and password.</p>
      <form onSubmit={submit}>
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <PasswordField
          label="Password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
          required
        />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary-button" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <div className="auth-links">
        <Link to="/forgot-password">Forgot password?</Link>
        <Link to="/register">Create a student account</Link>
      </div>
    </section>
  )
}
