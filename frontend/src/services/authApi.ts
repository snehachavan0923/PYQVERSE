import api from './api'
import { friendlyError } from './errors'
import type { AuthSession } from '../types/auth'

export function authHeaders(session: AuthSession | null) {
  return { Authorization: `Bearer ${session?.access_token ?? ''}` }
}

export async function getWithAuth<T>(
  path: string,
  session: AuthSession | null,
  timeout = 20_000,
): Promise<T> {
  const response = await api.get<T>(path, { headers: authHeaders(session), timeout })
  return response.data
}

export async function postWithAuth<T>(
  path: string,
  session: AuthSession | null,
  body?: unknown,
): Promise<T> {
  const response = await api.post<T>(path, body, { headers: authHeaders(session) })
  return response.data
}

export async function patchWithAuth<T>(
  path: string,
  session: AuthSession | null,
  body?: unknown,
): Promise<T> {
  const response = await api.patch<T>(path, body, { headers: authHeaders(session) })
  return response.data
}

export async function uploadWithAuth<T>(
  path: string,
  session: AuthSession | null,
  formData: FormData,
): Promise<T> {
  const response = await api.post<T>(path, formData, {
    headers: { ...authHeaders(session), 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

export async function deleteWithAuth<T>(path: string, session: AuthSession | null): Promise<T> {
  const response = await api.delete<T>(path, { headers: authHeaders(session) })
  return response.data
}

export function errorDetail(err: unknown, fallback: string): string {
  return friendlyError(err, fallback)
}
