import 'server-only'

import { awaitDelay, rememberDelay } from './advertised-delay'
import { ApiError, rawFetch, type ApiRequest, type ApiResponse } from './client'
import { accessTokenFor, refreshAfterUnauthorized, SessionGone } from './session-store'
import { currentSessionId } from '@lib/session'

/**
 * Authorized server-side call: refreshes once on a 401 and replays the request exactly once.
 *
 * It is also where a delay the API advertised is honoured. Every outbound call passes through here
 * — the server renders, the read proxy, the search write handlers, the rationed reads — and the
 * window the API opens belongs to the route template and the session, not to any one of them. So
 * the wait is taken once, here, and nothing above has to know the rule.
 */
export async function callApi<T>(req: Omit<ApiRequest<T>, 'token'>): Promise<ApiResponse<T>> {
  const sid = await currentSessionId()
  if (!sid) throw new SessionGone()

  await awaitDelay(sid, req.path, req.signal)

  const token = await accessTokenFor(sid)
  try {
    return await rawFetch<T>({ ...req, token })
  } catch (error) {
    if (error instanceof ApiError) rememberDelay(sid, req.path, error.retryAfterMs)
    if (!(error instanceof ApiError) || error.status !== 401) throw error
    const refreshed = await refreshAfterUnauthorized(sid)
    return await rawFetch<T>({ ...req, token: refreshed })
  }
}
