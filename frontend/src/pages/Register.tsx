import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { friendlyError } from '../services/errors'
import notifications from '../services/notification'
import { useAuth } from '../context/AuthContext'
import PasswordField from '../components/PasswordField'
import OtpInput from '../components/OtpInput'
import type { AuthSession } from '../types/auth'

interface RegisterResponse extends Partial<AuthSession> {
  email_verification_pending?: boolean
  profile?: AuthSession['profile']
}

const PASSWORD_POLICY = 'At least 8 characters with an uppercase letter, a lowercase letter and a number.'

function passwordIsStrong(password: string) {
  return password.length >= 8 && /[A-Z]/.test(password) && /[a-z]/.test(password) && /[0-9]/.test(password)
}

function maskEmailFallback(email: string): string {
  const parts = email.split('@')
  if (parts.length !== 2) return email
  const [local, domain] = parts
  if (local.length <= 1) return `*@${domain}`
  if (local.length <= 3) return `${local[0]}${'*'.repeat(local.length - 1)}@${domain}`
  return `${local[0]}*****@${domain}`
}

export default function Register() {
  const [form, setForm] = useState({ fullName: '', email: '', password: '', confirmPassword: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [submittedEmail, setSubmittedEmail] = useState('')

  // Verification step state
  const [verifyToken, setVerifyToken] = useState('')
  const [verifyLoading, setVerifyLoading] = useState(false)
  const [verifyError, setVerifyError] = useState('')
  const [countdown, setCountdown] = useState(60)
  const [resending, setResending] = useState(false)

  const { setSession } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (countdown <= 0) return
    const timer = setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(timer)
  }, [countdown])

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
      void notifications.toast('success', 'Confirmation message sent to your email')
      setSubmittedEmail(form.email.trim())
      setCountdown(60)
    } catch (err) {
      const message = friendlyError(err, 'Unable to register')
      setError(message)
      void notifications.error('Registration failed', message)
    } finally {
      setLoading(false)
    }
  }

  const submitVerification = async (event: FormEvent) => {
    event.preventDefault()
    if (verifyLoading) return
    const token = verifyToken.trim()
    if (token.length !== 6) {
      setVerifyError('Please enter the complete 6-digit verification code.')
      return
    }

    setVerifyLoading(true)
    setVerifyError('')
    try {
      const response = await api.post<AuthSession>(
        '/auth/otp/verify',
        { email: submittedEmail.toLowerCase(), token },
        { timeout: 20_000 },
      )
      setSession(response.data)
      void notifications.toast('success', 'Account confirmed and activated')
      navigate(response.data.profile.onboarding_completed ? '/student' : '/onboarding', { replace: true })
    } catch (err) {
      const message = friendlyError(err, 'Invalid or expired verification code')
      setVerifyError(message)
      void notifications.error('Verification failed', message)
    } finally {
      setVerifyLoading(false)
    }
  }

  const handleResend = async () => {
    if (countdown > 0 || resending) return
    setResending(true)
    setVerifyError('')
    try {
      await api.post<{ message: string }>(
        '/auth/resend-confirmation',
        { email: submittedEmail.toLowerCase() },
        { timeout: 20_000 },
      )
      setCountdown(60)
      void notifications.toast('success', 'Confirmation message resent')
    } catch (err) {
      const message = friendlyError(err, 'Unable to resend confirmation email')
      setVerifyError(message)
      void notifications.error('Resend failed', message)
    } finally {
      setResending(false)
    }
  }

  if (submittedEmail) {
    return (
      <section className="auth-card">
        <div className="brand-mark">PYQ</div>
        <p className="eyebrow">Account created</p>
        <h1>Please verify your email</h1>

        <div className="otp-confirmation-banner" role="status">
          <div className="otp-confirmation-header">
            <svg
              className="otp-confirmation-icon"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect width="20" height="16" x="2" y="4" rx="2" />
              <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
            </svg>
            <strong>Check your email</strong>
          </div>
          <p className="otp-confirmation-text">
            We&apos;ve sent a verification code to your registered email address{' '}
            <strong className="otp-confirmation-target">{maskEmailFallback(submittedEmail)}</strong>. Check your inbox. If you don&apos;t see it, check your Spam or Junk folder.
          </p>
        </div>

        <form onSubmit={submitVerification}>
          <label>
            Verification Code
            <OtpInput
              value={verifyToken}
              onChange={setVerifyToken}
              disabled={verifyLoading}
              hasError={Boolean(verifyError)}
            />
          </label>

          <div className="otp-resend-row">
            <Link to="/login" className="otp-back-btn">
              ← Sign in with password
            </Link>

            {countdown > 0 ? (
              <span>Resend in {countdown}s</span>
            ) : (
              <button
                type="button"
                className="otp-resend-btn"
                onClick={handleResend}
                disabled={resending || verifyLoading}
              >
                {resending ? 'Sending…' : 'Resend confirmation'}
              </button>
            )}
          </div>

          {verifyError && <p className="form-error" role="alert">{verifyError}</p>}

          <button
            className="primary-button"
            disabled={verifyLoading || verifyToken.trim().length !== 6}
          >
            {verifyLoading ? 'Activating account…' : 'Verify & Activate Account'}
          </button>
        </form>

        <p className="muted" style={{ marginTop: '16px' }}>
          Already confirmed your email? <Link to="/login">Sign in with password</Link>
        </p>
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
        {error && <p className="form-error" role="alert">{error}</p>}
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
