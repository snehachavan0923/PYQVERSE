import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import type { AuthSession } from '../types/auth'

interface RegisterResponse extends Partial<AuthSession> {
  email_verification_pending?: boolean
  profile?: AuthSession['profile']
}

const PASSWORD_POLICY = 'At least 8 characters with an uppercase letter, a lowercase letter and a number.'

function passwordIsStrong(password: string) {
  return password.length >= 8 && /[A-Z]/.test(password) && /[a-z]/.test(password) && /[0-9]/.test(password)
}

export default function Register() {
  const [form, setForm] = useState({ fullName: '', email: '', password: '', confirmPassword: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [submittedEmail, setSubmittedEmail] = useState('')
  const { setSession } = useAuth()
  const navigate = useNavigate()

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')

    if (!form.email.trim().toLowerCase().endsWith('@rvce.edu.in')) {
      setError('Student registration requires an @rvce.edu.in email address.')
      return
    }
    if (!passwordIsStrong(form.password)) {
      setError(`Password does not meet the requirements. ${PASSWORD_POLICY}`)
      return
    }
    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      const response = await api.post<RegisterResponse>('/auth/register', {
        email: form.email.trim(),
        password: form.password,
        confirm_password: form.confirmPassword,
        full_name: form.fullName.trim(),
      })
      const data = response.data
      if (data.access_token && data.refresh_token && data.user && data.profile && !data.email_verification_pending) {
        setSession({
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          user: data.user,
          profile: data.profile,
        })
        navigate('/onboarding')
        return
      }
      setSubmittedEmail(form.email.trim())
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string | { msg?: string }[] } } }).response?.data?.detail
      if (typeof detail === 'string') {
        setError(detail)
      } else if (Array.isArray(detail) && detail.length > 0) {
        setError(detail[0]?.msg ?? 'Unable to register')
      } else {
        setError('Unable to register')
      }
    } finally {
      setLoading(false)
    }
  }

  if (submittedEmail) {
    return (
      <section className="auth-card">
        <div className="brand-mark">PYQ</div>
        <p className="eyebrow">Check your inbox</p>
        <h1>Confirm your email</h1>
        <p className="muted">
          We sent a confirmation link to <strong>{submittedEmail}</strong>. Open that link to verify your
          account, then sign in with your email and password.
        </p>
        <p className="muted">If you do not see the message, check your spam folder.</p>
        <Link className="primary-button auth-button-link" to="/login">
          Back to sign in
        </Link>
      </section>
    )
  }

  return (
    <section className="auth-card">
      <div className="brand-mark">PYQ</div>
      <p className="eyebrow">Student access</p>
      <h1>Create your account</h1>
      <p className="muted">Use your official RVCE email address. Public registration always creates a student account.</p>
      <form onSubmit={submit}>
        <label>
          Full name
          <input
            autoComplete="name"
            value={form.fullName}
            onChange={(event) => setForm({ ...form, fullName: event.target.value })}
            required
          />
        </label>
        <label>
          RVCE email
          <input
            type="email"
            autoComplete="email"
            placeholder="name@rvce.edu.in"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
            required
          />
        </label>
        <label>
          Confirm password
          <input
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={form.confirmPassword}
            onChange={(event) => setForm({ ...form, confirmPassword: event.target.value })}
            required
          />
        </label>
        <p className="form-hint">{PASSWORD_POLICY}</p>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button" disabled={loading}>
          {loading ? 'Creating account...' : 'Create account'}
        </button>
      </form>
      <p className="muted">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </section>
  )
}
