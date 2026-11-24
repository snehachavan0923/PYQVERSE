import { useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { postWithAuth } from '../services/authApi'
import { friendlyError } from '../services/errors'
import notifications from '../services/notification'
import PasswordField from './PasswordField'

const POLICY = 'At least 8 characters with an uppercase letter, a lowercase letter and a number.'

function strong(value: string) {
  return value.length >= 8 && /[A-Z]/.test(value) && /[a-z]/.test(value) && /[0-9]/.test(value)
}

export default function PasswordChangeForm() {
  const { session } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (loading) return
    setError('')
    if (!strong(newPassword)) {
      setError(`New password does not meet the requirements. ${POLICY}`)
      return
    }
    if (newPassword !== confirmPassword) {
      setError('New passwords do not match.')
      return
    }
    if (newPassword === currentPassword) {
      setError('New password must differ from the current password.')
      return
    }
    setLoading(true)
    try {
      await postWithAuth('/auth/password/change', session, {
        current_password: currentPassword,
        new_password: newPassword,
      })
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      void notifications.toast('success', 'Password updated')
    } catch (err) {
      setError(friendlyError(err, 'Unable to update the password'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <PasswordField label="Current password" autoComplete="current-password" value={currentPassword} onChange={setCurrentPassword} required />
      <PasswordField label="New password" autoComplete="new-password" minLength={8} value={newPassword} onChange={setNewPassword} required />
      <PasswordField label="Confirm new password" autoComplete="new-password" minLength={8} value={confirmPassword} onChange={setConfirmPassword} required />
      <p className="form-hint">{POLICY}</p>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button className="primary-button compact-button" disabled={loading}>{loading ? 'Updating…' : 'Change password'}</button>
      </div>
    </form>
  )
}
