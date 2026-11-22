import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../services/supabase'

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
        setError(updateError.message)
        return
      }
      await supabase.auth.signOut()
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
          <label>
            New password
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <label>
            Confirm new password
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
            />
          </label>
          <p className="form-hint">{PASSWORD_POLICY}</p>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button" disabled={loading}>
            {loading ? 'Updating...' : 'Update password'}
          </button>
        </form>
      )}
      <p className="muted">
        <Link to="/login">Back to sign in</Link>
      </p>
    </section>
  )
}
