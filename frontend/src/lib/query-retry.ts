import { isHttpError } from '@api/http-error'

const MAX_ATTEMPTS = 3
const MAX_BACKOFF_MS = 30_000

/** Retry 429 and 5xx, never a plain 4xx, and never a session that is already gone. */
export function retry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_ATTEMPTS) return false
  if (!isHttpError(error)) return true
  if (error.code === 'session_revoked') return false
  if (error.status === 429) return true
  if (error.status >= 400 && error.status < 500) return false
  return true
}

export function retryDelay(failureCount: number, error: unknown): number {
  const backoff = Math.min(1000 * 2 ** failureCount, MAX_BACKOFF_MS)
  if (isHttpError(error) && error.retryAfterMs !== null && error.retryAfterMs > 0) {
    return Math.max(backoff, error.retryAfterMs)
  }
  return backoff
}
