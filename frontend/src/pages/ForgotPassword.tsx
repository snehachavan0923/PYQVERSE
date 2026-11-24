import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import api from '../services/api'
import { friendlyError } from '../services/errors'
import notifications from '../services/notification'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setLoading(true)
    try {
      const response = await api.post<{ message: string }>('/auth/password-reset/request', { email })
      setMessage(response.data.message)
      void notifications.toast('success', 'Reset request submitted')
    } catch (err) {
      setError(friendlyError(err, 'Unable to request a password reset'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="auth-card">
      <div className="brand-mark">PYQ</div>
      <p className="eyebrow">Account recovery</p>
      <h1>Reset your password</h1>
      <p className="muted">Enter your account email and we will send a Supabase password recovery link.</p>
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
        {error && <p className="form-error">{error}</p>}
        {message && <p className="form-notice" role="status">{message}</p>}
        <button className="primary-button" disabled={loading}>
          {loading ? 'Sending...' : 'Send reset link'}
        </button>
      </form>
      <p className="muted">
        <Link to="/login">Back to sign in</Link>
      </p>
    </section>
  )
}
