import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'

export default function Register() {
  const [form, setForm] = useState({ email: '', password: '', fullName: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (!form.email.toLowerCase().endsWith('@rvce.edu.in')) {
      setError('Student registration requires an @rvce.edu.in email')
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
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Unable to register')
    } finally {
      setLoading(false)
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
          <input type="password" minLength={8} value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button" disabled={loading}>{loading ? 'Creating...' : 'Create account'}</button>
      </form>
      <p className="muted">Already have an account? <Link to="/login">Sign in</Link></p>
    </section>
  )
}
