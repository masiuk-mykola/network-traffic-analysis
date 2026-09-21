import { reportFailure } from '@lib/auth/session-expiry'

import { HttpError } from './http-error'

/**
 * The only way the browser reads the API: through our proxy, which adds the token on the server.
 * Nothing here may import a `server-only` module, and it never sets credentials of its own —
 * the session cookie rides along as a same-origin cookie.
 */
export async function fetchJson<T>(
  path: string,
  options: { query?: URLSearchParams; signal?: AbortSignal } = {},
): Promise<T> {
  const { query, signal } = options
  const search = query && [...query].length > 0 ? `?${query}` : ''
  const res = await fetch(`/api/capture/${path.replace(/^\/+/, '')}${search}`, {
    headers: { accept: 'application/json' },
    signal,
  })

  if (!res.ok) {
    const failure = await HttpError.fromResponse(res)
    // Every browser read passes through here, so this is where a dead session is noticed —
    // whether or not the caller happens to be a React Query hook.
    reportFailure(failure)
    throw failure
  }

  return (await res.json()) as T
}
