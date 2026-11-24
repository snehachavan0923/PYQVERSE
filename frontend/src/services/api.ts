import axios from 'axios'
import { friendlyError } from './errors'

export const SESSION_EXPIRED_EVENT = 'pyqverse:session-expired'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

const PUBLIC_AUTH_PATHS = [
  '/auth/login',
  '/auth/register',
  '/auth/refresh',
  '/auth/password-reset',
]

function isPublicAuthRequest(url?: string): boolean {
  if (!url) return false
  return PUBLIC_AUTH_PATHS.some((path) => url.includes(path))
}

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const candidate = error as {
      response?: { status?: number }
      config?: { url?: string }
      friendlyMessage?: string
    }
    candidate.friendlyMessage = friendlyError(error)
    if (candidate.response?.status === 401 && !isPublicAuthRequest(candidate.config?.url)) {
      try {
        localStorage.removeItem('pyqverse_session')
      } catch {
        // Ignore storage failures; in-memory state is still cleared by AuthContext.
      }
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
    }
    return Promise.reject(error)
  },
)

export default api
