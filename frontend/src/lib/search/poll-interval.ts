export const START_POLL_MS = 500
export const MAX_POLL_MS = 5000

/**
 * How long to wait before asking about a running job again. Quick at first, because a search over
 * this capture can finish in a second; then doubling to a ceiling, so a long one does not produce a
 * request per second for minutes — the API counts identical reads made in the same instant.
 */
export function nextPollDelay(attempt: number): number {
  if (!Number.isFinite(attempt) || attempt <= 0) return START_POLL_MS
  return Math.min(START_POLL_MS * 2 ** attempt, MAX_POLL_MS)
}
