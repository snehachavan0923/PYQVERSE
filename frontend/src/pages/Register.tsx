import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { notification } from '../services/notification'

export default function Register() {
  const [form, setForm] = useState({ email: '', password: '', fullName: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const submitting = useRef(false)
  const navigate = useNavigate()

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true
    setError('')
    if (!form.email.toLowerCase().endsWith('@rvce.edu.in')) {
      setError('Student registration requires an @rvce.edu.in email')
      await notification.warning('Check your email', 'Student registration requires an @rvce.edu.in email.')
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/register', {
        email: form.email,
        password: form.password,
        full_name: form.fullName,
      })
      navigate('/verify-otp', { state: { email: form.email, purpose: 'signup' } })
      await notification.success('Check your email', 'Supabase will deliver your real verification OTP.')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Unable to register')
      await notification.error('Registration failed', err.response?.data?.detail ?? 'Unable to register')
    } finally {
      setLoading(false)
      submitting.current = false
    }
  }

  return (
    <section className="auth-card">
      <div className="brand-mark">PYQ</div>
      <p className="eyebrow">Student access</p>
      <h1>Create your account</h1>
      <p className="muted">Use your official RVCE email address.</p>
      <form onSubmit={submit}>
        <label>Full name
          <input value={form.fullName} onChange={(event) => setForm({ ...form, fullName: event.target.value })} required />
        </label>
        <label>RVCE email
          <input type="email" placeholder="name@rvce.edu.in" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
        </label>
        <label>Password
          <span className="password-field">
            <input
              type={showPassword ? 'text' : 'password'}
              minLength={8}
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              required
              autoComplete="new-password"
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
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button" disabled={loading}>{loading ? 'Creating...' : 'Create account'}</button>
      </form>
      <p className="muted">Already have an account? <Link to="/login">Sign in</Link></p>
    </section>
  )
}
