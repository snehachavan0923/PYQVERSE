import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { friendlyError } from '../services/errors'
import notifications from '../services/notification'
import { useAuth } from '../context/AuthContext'
import PasswordField from '../components/PasswordField'
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
    if (loading) return
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
        void notifications.toast('success', 'Student account created')
        navigate('/onboarding', { replace: true })
        return
      }
      void notifications.toast('success', 'Confirmation email sent')
      setSubmittedEmail(form.email.trim())
    } catch (err) {
      void notifications.error('Registration failed', friendlyError(err, 'Unable to register'))
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
        <PasswordField
          label="Password"
          autoComplete="new-password"
          value={form.password}
          onChange={(value) => setForm({ ...form, password: value })}
          minLength={8}
          required
        />
        <PasswordField
          label="Confirm password"
          autoComplete="new-password"
          value={form.confirmPassword}
          onChange={(value) => setForm({ ...form, confirmPassword: value })}
          minLength={8}
          required
        />
        <p className="form-hint">{PASSWORD_POLICY}</p>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button" disabled={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <p className="muted">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </section>
  )
}
