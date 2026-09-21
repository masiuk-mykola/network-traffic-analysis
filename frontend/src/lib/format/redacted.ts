/**
 * An observer is shown a marker instead of a sensitive value — a cookie, an authorization header,
 * a mail recipient, a user name. It is recognised by its shape, so an ordinary value that happens to
 * mention the word is never hidden.
 */
export const WITHHELD = 'Withheld for your role'

export function isRedacted(value: unknown): boolean {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    (value as Record<string, unknown>).redacted === true
  )
}
