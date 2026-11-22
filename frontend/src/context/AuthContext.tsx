import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import api from '../services/api'
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSessionState] = useState<AuthSession | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem('pyqverse_session')
    if (saved) {
      try {
        setSessionState(JSON.parse(saved))
      } catch {
        localStorage.removeItem('pyqverse_session')
      }
    }
    setLoading(false)

    if (!supabase) return
    const { data } = supabase.auth.onAuthStateChange((_event, supabaseSession) => {
      if (!supabaseSession) {
        setSessionState(null)
        localStorage.removeItem('pyqverse_session')
      }
    })
    return () => data.subscription.unsubscribe()
  }, [])

  const setSession = (value: AuthSession | null) => {
    setSessionState(value)
    if (value) localStorage.setItem('pyqverse_session', JSON.stringify(value))
    else localStorage.removeItem('pyqverse_session')
  }

  const logout = async () => {
    if (session?.access_token) {
      try {
        await api.post('/auth/logout', undefined, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        })
      } catch {
        // Clear the local session even if the server session has already expired.
      }
    }
    await supabase?.auth.signOut()
    setSession(null)
  }

  const value = useMemo(
    () => ({ session, profile: session?.profile ?? null, loading, setSession, logout }),
    [session, loading],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
