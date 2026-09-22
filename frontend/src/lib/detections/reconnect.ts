/**
 * How long to wait before opening the feed again.
 *
 * The API grades two things about a re-opening: that it does not follow a close by less than a
 * second, and that no two opens fall within a second of each other. Under its storm profile it ends
 * the stream itself every twenty seconds, so this is the ordinary path, not the error path — the
 * policy is what keeps a normal day from reading as a careless client.
 *
 * The server states its own preference when it opens the stream (`retry: 3000`). That is the floor
 * in the ordinary case; only repeated failures to open lengthen it, and only to a ceiling.
 */

/** Above the server's one-second threshold, never on it — a pause measured at both ends needs room. */
export const MIN_RECONNECT_MS = 1_500

/** What the server asks for when it opens the stream. */
export const SERVER_HINT_MS = 3_000

export const MAX_RECONNECT_MS = 30_000

/** Why the stream ended. Only `error` counts as a failure worth backing off from. */
export type EndReason = 'rotate' | 'reauth' | 'reset' | 'error'

export type Attempt = {
  reason: EndReason
  /** Consecutive failures to open. Reset to zero by a successful open. */
  failures: number
  /** A `retry:` the server sent, when it sent one longer than our own floor. */
  hintMs?: number
}

export function reconnectDelay({ reason, failures, hintMs }: Attempt): number {
  const floor = Math.max(MIN_RECONNECT_MS, SERVER_HINT_MS, hintMs ?? 0)
  if (reason !== 'error') return Math.min(floor, MAX_RECONNECT_MS)

  const attempts = Number.isFinite(failures) ? Math.max(0, Math.trunc(failures)) : 0
  const backoff = floor * 2 ** Math.max(0, attempts - 1)
  return Math.min(Math.max(backoff, floor), MAX_RECONNECT_MS)
}
