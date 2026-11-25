export interface ApiErrorLike {
  response?: {
    status?: number
    data?: { code?: unknown; detail?: unknown }
  }
  message?: string
  code?: string
}

const STATUS_FALLBACKS: Record<number, string> = {
  400: 'The request could not be completed. Check the submitted information.',
  401: 'Your session is no longer valid. Please sign in again.',
  403: 'You do not have permission to perform this action.',
  404: 'The requested item could not be found.',
  409: 'This action conflicts with existing data.',
  413: 'The uploaded file is too large.',
  415: 'That file type is not supported.',
  422: 'Some submitted information is invalid.',
  429: 'Too many requests. Please wait and try again.',
  500: 'Something went wrong on our side. Please try again.',
  503: 'An external service is temporarily unavailable. Please try again shortly.',
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    for (const item of detail) {
      if (typeof item === 'string' && item.trim()) return item
      if (item && typeof item === 'object' && 'msg' in item) {
        const message = (item as { msg?: unknown }).msg
        if (typeof message === 'string' && message.trim()) return message
      }
    }
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message
  }
  return null
}

export function friendlyError(err: unknown, fallback = 'Unable to complete the request'): string {
  const candidate = err as ApiErrorLike
  const status = candidate?.response?.status
  const errorCode = candidate?.response?.data?.code
  if (errorCode === 'DATABASE_SCHEMA_ERROR') {
    return "The server's data schema is out of date. Please contact an administrator."
  }
  if (status === 500) return STATUS_FALLBACKS[500]
  const detail = detailMessage(candidate?.response?.data?.detail)
  if (detail) return detail
  if (status && STATUS_FALLBACKS[status]) return STATUS_FALLBACKS[status]
  if (candidate?.code === 'ECONNABORTED' || candidate?.code === 'ETIMEDOUT') {
    return 'The request took too long to complete. Check your connection and try again.'
  }
  if (candidate?.code === 'ERR_NETWORK' || candidate?.message === 'Network Error') {
    return 'Unable to reach the PYQVERSE server. Check your connection and try again.'
  }
  return fallback
}

export function isNetworkError(err: unknown): boolean {
  const candidate = err as ApiErrorLike
  return candidate?.code === 'ERR_NETWORK' || candidate?.message === 'Network Error'
}
