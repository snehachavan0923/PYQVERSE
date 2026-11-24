import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import api, { SESSION_EXPIRED_EVENT } from '../services/api'
import notifications from '../services/notification'
import { supabase } from '../services/supabase'
import type { AuthProfile, AuthSession } from '../types/auth'

interface AuthContextValue {
  session: AuthSession | null
  profile: AuthProfile | null
  loading: boolean
  setSession: (session: AuthSession | null) => void
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

let sessionRestoreInFlight: Promise<AuthSession | null> | null = null

function restoreStoredSession(): Promise<AuthSession | null> {
  if (sessionRestoreInFlight) return sessionRestoreInFlight

  const saved = localStorage.getItem('pyqverse_session')
  if (!saved) return Promise.resolve(null)

  const restore = (async () => {
    try {
      const previous = JSON.parse(saved) as AuthSession
      if (!previous.refresh_token) return null

      const refreshed = await api.post<Omit<AuthSession, 'profile'>>('/auth/refresh', {
        refresh_token: previous.refresh_token,
      })
      const currentUser = await api.get<{
        id: string
        role: AuthProfile['role']
        onboarding_completed: boolean
      }>('/auth/me', {
        headers: { Authorization: `Bearer ${refreshed.data.access_token}` },
      })

      return {
        ...refreshed.data,
        profile: {
          id: currentUser.data.id,
          role: currentUser.data.role,
          onboarding_completed: currentUser.data.onboarding_completed,
        },
      }
    } catch {
      localStorage.removeItem('pyqverse_session')
      return null
    }
  })()

  sessionRestoreInFlight = restore
  void restore.finally(() => {
    if (sessionRestoreInFlight === restore) sessionRestoreInFlight = null
  })
  return restore
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSessionState] = useState<AuthSession | null>(null)
  const [loading, setLoading] = useState(true)

  const setSession = useCallback((value: AuthSession | null) => {
    setSessionState(value)
    if (value) localStorage.setItem('pyqverse_session', JSON.stringify(value))
    else localStorage.removeItem('pyqverse_session')
  }, [])

  useEffect(() => {
    let active = true

    const restoreSession = async () => {
      try {
        const restored = await restoreStoredSession()
        if (active) setSession(restored)
      } finally {
        if (active) setLoading(false)
      }
    }

    void restoreSession()

    let notifiedExpiry = false
    const handleExpiry = () => {
      setSession(null)
      if (notifiedExpiry) return
      notifiedExpiry = true
      void notifications.warning('Session expired', 'Please sign in again to continue.')
      window.setTimeout(() => {
        notifiedExpiry = false
      }, 4000)
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpiry)

    const { data } = supabase
      ? supabase.auth.onAuthStateChange((event, supabaseSession) => {
          if (event === 'SIGNED_OUT' && !supabaseSession) setSession(null)
        })
      : { data: { subscription: { unsubscribe: () => undefined } } }

    return () => {
      active = false
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpiry)
      data.subscription.unsubscribe()
    }
  }, [setSession])

  const logout = useCallback(async () => {
    if (session?.access_token) {
      try {
        await api.post('/auth/logout', undefined, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        })
      } catch {
        // Clear the local session even if the server session has already expired.
      }
    }
    try {
      await supabase?.auth.signOut()
    } catch {
      // The backend logout already ran; local state must still be cleared.
    } finally {
      setSession(null)
    }
  }, [session, setSession])

  const value = useMemo(
    () => ({ session, profile: session?.profile ?? null, loading, setSession, logout }),
    [session, loading, setSession, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
