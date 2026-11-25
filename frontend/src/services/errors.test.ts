import { describe, expect, it } from 'vitest'
import { friendlyError } from './errors'

describe('friendlyError', () => {
  it('shows a sanitized message for a database schema mismatch', () => {
    const message = friendlyError({
      response: {
        status: 500,
        data: {
          code: 'DATABASE_SCHEMA_ERROR',
          detail: 'UndefinedColumn: SELECT secret FROM private_table',
        },
      },
    })

    expect(message).toBe("The server's data schema is out of date. Please contact an administrator.")
    expect(message).not.toContain('SELECT')
  })

  it('does not expose server details from other HTTP 500 responses', () => {
    expect(
      friendlyError({
        response: { status: 500, data: { detail: 'database password leaked in stack trace' } },
      }),
    ).toBe('Something went wrong on our side. Please try again.')
  })

  it('distinguishes an HTTP 500 from a network failure', () => {
    expect(friendlyError({ code: 'ERR_NETWORK', message: 'Network Error' })).toBe(
      'Unable to reach the PYQVERSE server. Check your connection and try again.',
    )
    expect(friendlyError({ response: { status: 500 } })).toBe(
      'Something went wrong on our side. Please try again.',
    )
  })
})
