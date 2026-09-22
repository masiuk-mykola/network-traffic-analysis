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

/** What the last refusal asked for, and how long ago it asked. */
export type AdvertisedWait = { retryAfterMs: number | null; elapsedMs: number }

/**
 * How long to wait before asking about a running job again, given what the server last said.
 *
 * The cadence above is ours, but a refusal that named a delay outranks it: the API scores an ask
 * made before the advertised delay, and the poll's own timer knows nothing about a 503 that arrived
 * between two ticks. Whichever wait is longer wins.
 */
export function pollDelay(attempt: number, wait?: AdvertisedWait): number {
  const base = nextPollDelay(attempt)
  if (!wait || wait.retryAfterMs === null || wait.retryAfterMs <= 0) return base

  const remaining = wait.retryAfterMs - wait.elapsedMs
  return Math.max(base, remaining)
}
