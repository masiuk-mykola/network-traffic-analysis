/**
 * Shared by the server client and the browser client, so both wait the same way.
 * The API sends `Retry-After` as seconds (429/503) or as an HTTP-date (login).
 */
export function parseRetryAfter(value: string | null, now = Date.now()): number | null {
  if (!value) return null
  const seconds = Number(value)
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000)
  const date = Date.parse(value)
  if (Number.isNaN(date)) return null
  return Math.max(0, date - now)
}
