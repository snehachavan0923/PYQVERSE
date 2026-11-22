import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import type { AuthSession } from '../types/auth'

export default function VerifyOtp() {
  const location = useLocation()
  const state = location.state as { email?: string; purpose?: 'signup' | 'login' } | null
  const [email, setEmail] = useState(state?.email ?? '')
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { setSession } = useAuth()
  const navigate = useNavigate()
  const purpose = state?.purpose ?? 'signup'

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const response = await api.post<AuthSession & { profile: { onboarding_completed: boolean; role: 'STUDENT' | 'ADMIN_FACULTY' } }>(
        '/auth/verify-otp',
        { email, token, purpose },
      )
      setSession(response.data)
      navigate(response.data.profile.role === 'ADMIN_FACULTY'
        ? '/admin'
        : response.data.profile.onboarding_completed ? '/student' : '/onboarding')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'OTP verification failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="auth-card">
      <div className="brand-mark">PYQ</div>
      <p className="eyebrow">Email verification</p>
      <h1>Enter your OTP</h1>
      <p className="muted">Use the real verification code delivered by Supabase.</p>
      <form onSubmit={submit}>
        <label>Email
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label>One-time code
          <input inputMode="numeric" value={token} onChange={(event) => setToken(event.target.value)} required />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button" disabled={loading}>{loading ? 'Verifying...' : 'Verify email'}</button>
      </form>
    </section>
  )
}
