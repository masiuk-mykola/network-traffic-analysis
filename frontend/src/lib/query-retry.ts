export type HttpError = { status: number; code?: string; retryAfterMs?: number | null }

const MAX_ATTEMPTS = 3

function isHttpError(error: unknown): error is HttpError {
  return typeof error === 'object' && error !== null && 'status' in error
}

/** Retry 429 and 5xx, never a plain 4xx. */
export function retry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_ATTEMPTS) return false
  if (!isHttpError(error)) return true
  if (error.status === 429) return true
  if (error.status >= 400 && error.status < 500) return false
  return true
}

export function retryDelay(failureCount: number, error: unknown): number {
  const backoff = Math.min(1000 * 2 ** failureCount, 30_000)
  if (isHttpError(error) && typeof error.retryAfterMs === 'number' && error.retryAfterMs > 0) {
    return Math.max(backoff, error.retryAfterMs)
  }
  return backoff
}
