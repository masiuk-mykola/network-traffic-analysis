import { DEFAULT_TARGET, ROUTES } from '@lib/routes'

/**
 * The destination carried through sign-in arrives from the URL, so it is attacker-controlled: it
 * must be a path inside this app and nothing else. Everything questionable collapses to the default
 * rather than being repaired.
 */
export function safeRedirectTarget(value: string | null | undefined): string {
  if (!value) return DEFAULT_TARGET

  const decoded = decodeOnce(value)
  if (!decoded.startsWith('/')) return DEFAULT_TARGET
  // `//host` and `/\host` are both ways of leaving the site.
  if (decoded.startsWith('//') || decoded.startsWith('/\\')) return DEFAULT_TARGET
  if (decoded.includes('\\')) return DEFAULT_TARGET
  if (decoded.startsWith(ROUTES.signIn)) return DEFAULT_TARGET

  return decoded
}

function decodeOnce(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    // A malformed escape is not a path we are willing to trust.
    return ''
  }
}
