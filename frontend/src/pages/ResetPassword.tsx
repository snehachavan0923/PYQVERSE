import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../services/supabase'
import notifications from '../services/notification'
import PasswordField from '../components/PasswordField'

const PASSWORD_POLICY = 'At least 8 characters with an uppercase letter, a lowercase letter and a number.'

function passwordIsStrong(password: string) {
  return password.length >= 8 && /[A-Z]/.test(password) && /[a-z]/.test(password) && /[0-9]/.test(password)
}

export default function ResetPassword() {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [ready, setReady] = useState(false)
  const [completed, setCompleted] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!supabase) return
    let active = true

    supabase.auth.getSession().then(({ data }) => {
      if (active && data.session) setReady(true)
    })
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (active && (event === 'PASSWORD_RECOVERY' || session)) setReady(true)
    })
    return () => {
      active = false
      data.subscription.unsubscribe()
    }
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (loading) return
    setError('')
    if (!supabase) {
      setError('Supabase authentication is not configured.')
      return
    }
    if (!passwordIsStrong(password)) {
      setError(`Password does not meet the requirements. ${PASSWORD_POLICY}`)
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    try {
      const { error: updateError } = await supabase.auth.updateUser({ password })
      if (updateError) {
        await notifications.error(
          'Password not updated',
          'The recovery link may have expired. Request a new password reset link and try again.',
        )
        return
      }
      await supabase.auth.signOut()
      void notifications.toast('success', 'Password updated')
      setCompleted(true)
    } finally {
      setLoading(false)
    }
  }

  if (completed) {
    return (
      <section className="auth-card">
        <div className="brand-mark">PYQ</div>
        <p className="eyebrow">Password updated</p>
        <h1>Your password has been changed</h1>
        <p className="muted">Sign in with your new password to continue.</p>
        <button className="primary-button" type="button" onClick={() => navigate('/login')}>
          Go to sign in
        </button>
      </section>
    )
  }

  return (
    <section className="auth-card">
      <div className="brand-mark">PYQ</div>
      <p className="eyebrow">Account recovery</p>
      <h1>Choose a new password</h1>
      {!supabase ? (
        <p className="form-error">Supabase authentication is not configured for this environment.</p>
      ) : !ready ? (
        <p className="muted">
          Open the password recovery link from your email to continue. If the link has expired, request a new
          one from the <Link to="/forgot-password">forgot password</Link> page.
        </p>
      ) : (
        <form onSubmit={submit}>
          <PasswordField
            label="New password"
            autoComplete="new-password"
            value={password}
            onChange={setPassword}
            minLength={8}
            required
          />
          <PasswordField
            label="Confirm new password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={setConfirmPassword}
            minLength={8}
            required
          />
          <p className="form-hint">{PASSWORD_POLICY}</p>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button" disabled={loading}>
            {loading ? 'Updating…' : 'Update password'}
          </button>
        </form>
      )}
      <p className="muted">
        <Link to="/login">Back to sign in</Link>
      </p>
    </section>
  )
}
