import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { friendlyError } from '../services/errors'
import notifications from '../services/notification'
import { useAuth } from '../context/AuthContext'
import PasswordField from '../components/PasswordField'
import OtpInput from '../components/OtpInput'
import type { AuthSession, LoginMethod } from '../types/auth'

function maskEmailFallback(email: string): string {
  const parts = email.split('@')
  if (parts.length !== 2) return email
  const [local, domain] = parts
  if (local.length <= 1) return `*@${domain}`
  if (local.length <= 3) return `${local[0]}${'*'.repeat(local.length - 1)}@${domain}`
  return `${local[0]}*****@${domain}`
}

export default function Login() {
  const [method, setMethod] = useState<LoginMethod>('password')

  // Password login state
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // OTP login state
  const [otpStep, setOtpStep] = useState<'request' | 'verify'>('request')
  const [otpEmail, setOtpEmail] = useState('')
  const [otpToken, setOtpToken] = useState('')
  const [maskedEmail, setMaskedEmail] = useState('')
  const [countdown, setCountdown] = useState(0)

  // Common UI state
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const { setSession } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (countdown <= 0) return
    const timer = setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(timer)
  }, [countdown])

  const switchMethod = (newMethod: LoginMethod) => {
    setMethod(newMethod)
    setError('')
  }

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

  // Password submission
  const submitPassword = async (event: FormEvent) => {
    event.preventDefault()
    if (submitting.current) return
    const formEl = event.currentTarget as HTMLFormElement
    const domEmail = (formEl.querySelector('input[name="email"]') as HTMLInputElement)?.value
    const domPassword = (formEl.querySelector('input[name="password"]') as HTMLInputElement)?.value

    const emailToUse = (domEmail ?? email).trim().toLowerCase()
    const passwordToUse = domPassword !== undefined && domPassword !== '' ? domPassword : password

    if (!emailToUse) return
    submitting.current = true
    setError('')
    setLoading(true)
    try {
      const response = await api.post<AuthSession>(
        '/auth/login',
        { email: emailToUse, password: passwordToUse },
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

  // OTP Request submission
  const submitOtpRequest = async (event: FormEvent) => {
    event.preventDefault()
    if (submitting.current) return
    const cleanEmail = otpEmail.trim().toLowerCase()
    if (!cleanEmail) return

    submitting.current = true
    setError('')
    setLoading(true)
    try {
      const response = await api.post<{ message: string; email: string }>(
        '/auth/otp/request',
        { email: cleanEmail },
        { timeout: 20_000 },
      )
      setMaskedEmail(response.data.email || maskEmailFallback(cleanEmail))
      setOtpStep('verify')
      setCountdown(60)
      setOtpToken('')
      void notifications.toast('success', 'Verification code sent to your email')
    } catch (err) {
      const message = friendlyError(err, 'Unable to send verification code')
      setError(message)
      void notifications.error('Request failed', message)
    } finally {
      submitting.current = false
      setLoading(false)
    }
  }

  // Resend OTP code
  const handleResend = async () => {
    if (countdown > 0 || resending) return
    setResending(true)
    setError('')
    try {
      const response = await api.post<{ message: string; email: string }>(
        '/auth/otp/request',
        { email: otpEmail.trim().toLowerCase() },
        { timeout: 20_000 },
      )
      setMaskedEmail(response.data.email || maskEmailFallback(otpEmail.trim()))
      setCountdown(60)
      void notifications.toast('success', 'A new verification code has been sent')
    } catch (err) {
      const message = friendlyError(err, 'Unable to resend verification code')
      setError(message)
      void notifications.error('Resend failed', message)
    } finally {
      setResending(false)
    }
  }

  // OTP Verification submission
  const submitOtpVerify = async (event: FormEvent) => {
    event.preventDefault()
    if (submitting.current) return
    const cleanToken = otpToken.trim()
    if (cleanToken.length !== 6) {
      setError('Please enter the complete 6-digit verification code.')
      return
    }

    submitting.current = true
    setError('')
    setLoading(true)
    try {
      const response = await api.post<AuthSession>(
        '/auth/otp/verify',
        { email: otpEmail.trim().toLowerCase(), token: cleanToken },
        { timeout: 20_000 },
      )
      enterSession(response.data)
    } catch (err) {
      const message = friendlyError(err, 'Invalid or expired verification code')
      setError(message)
      void notifications.error('Verification failed', message)
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
      <p className="muted">
        {method === 'password'
          ? 'Sign in to your PYQVERSE workspace with your email and password.'
          : otpStep === 'request'
            ? 'Sign in password-free with a verification code sent to your registered college email.'
            : 'Enter the 6-digit verification code to complete sign-in.'}
      </p>

      {/* Authentication Method Selector */}
      <div className="auth-method-selector" role="tablist" aria-label="Sign-in methods">
        <button
          type="button"
          role="tab"
          aria-selected={method === 'password'}
          className={`auth-method-button ${method === 'password' ? 'active' : ''}`}
          onClick={() => switchMethod('password')}
        >
          Password Login
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={method === 'otp'}
          className={`auth-method-button ${method === 'otp' ? 'active' : ''}`}
          onClick={() => switchMethod('otp')}
        >
          Email OTP
        </button>
      </div>

      {method === 'password' && (
        <form onSubmit={submitPassword}>
          <label>
            Email
            <input
              type="email"
              name="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <PasswordField
            label="Password"
            name="password"
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
      )}

      {method === 'otp' && otpStep === 'request' && (
        <form onSubmit={submitOtpRequest}>
          <label>
            Registered College Email
            <input
              type="email"
              autoComplete="email"
              placeholder="student@rvce.edu.in"
              value={otpEmail}
              onChange={(event) => setOtpEmail(event.target.value)}
              required
            />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" disabled={loading}>
            {loading ? 'Sending code…' : 'Send Verification Code'}
          </button>
        </form>
      )}

      {method === 'otp' && otpStep === 'verify' && (
        <form onSubmit={submitOtpVerify}>
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
              {maskedEmail && <strong className="otp-confirmation-target">{maskedEmail}</strong>}. Check your inbox. If you don&apos;t see it, check your Spam or Junk folder.
            </p>
          </div>

          <label>
            Verification Code
            <OtpInput
              value={otpToken}
              onChange={setOtpToken}
              disabled={loading}
              hasError={Boolean(error)}
            />
          </label>

          <div className="otp-resend-row">
            <button
              type="button"
              className="otp-back-btn"
              onClick={() => {
                setOtpStep('request')
                setError('')
              }}
              disabled={loading}
            >
              ← Change email
            </button>

            {countdown > 0 ? (
              <span>Resend code in {countdown}s</span>
            ) : (
              <button
                type="button"
                className="otp-resend-btn"
                onClick={handleResend}
                disabled={resending || loading}
              >
                {resending ? 'Sending…' : 'Resend Code'}
              </button>
            )}
          </div>

          {error && <p className="form-error" role="alert">{error}</p>}

          <button
            className="primary-button"
            disabled={loading || otpToken.trim().length !== 6}
          >
            {loading ? 'Verifying…' : 'Verify Code'}
          </button>
        </form>
      )}

      <div className="auth-links">
        <Link to="/forgot-password">Forgot password?</Link>
        <Link to="/register">Create a student account</Link>
      </div>
    </section>
  )
}
