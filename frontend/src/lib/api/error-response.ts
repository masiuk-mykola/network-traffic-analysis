import 'server-only'

import { logServerError } from '@lib/log'

import { ApiError, SchemaMismatchError } from './client'
import { SessionGone } from './session-store'

export type ErrorPayload = {
  status: number
  body: Record<string, unknown>
  headers?: Record<string, string>
}

/**
 * Maps a failure from the API layer to what the browser is allowed to see, or null when the
 * failure is not ours to explain — the caller rethrows those. An upstream contract problem is
 * logged here and reported as a plain 502: its details describe our server, not the request.
 */
export function toErrorPayload(error: unknown): ErrorPayload | null {
  if (error instanceof SessionGone) {
    return { status: 401, body: { code: 'session_revoked', detail: 'sign in again' } }
  }

  if (error instanceof SchemaMismatchError) {
    logServerError('api', `${error.message} — ${error.issues.join('; ')}`)
    return {
      status: 502,
      body: { code: 'upstream_contract', detail: 'unexpected response from the API' },
    }
  }

  if (error instanceof ApiError) {
    const body = error.body ?? { code: error.code, detail: error.message }
    if (error.retryAfterMs === null) return { status: error.status, body }
    return {
      status: error.status,
      body,
      headers: { 'retry-after': String(Math.ceil(error.retryAfterMs / 1000)) },
    }
  }

  return null
}
