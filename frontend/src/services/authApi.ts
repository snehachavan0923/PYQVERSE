import api from './api'
import type { AuthSession } from '../types/auth'

export function authHeaders(session: AuthSession | null) {
  return { Authorization: `Bearer ${session?.access_token ?? ''}` }
}

export async function getWithAuth<T>(path: string, session: AuthSession | null): Promise<T> {
  const response = await api.get<T>(path, { headers: authHeaders(session) })
  return response.data
}

export function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
  return detail ?? fallback
}
