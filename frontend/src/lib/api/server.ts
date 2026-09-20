import 'server-only'

import { ApiError, rawFetch, type ApiRequest, type ApiResponse } from './client'
import { accessTokenFor, refreshAfterUnauthorized, SessionGone } from './session-store'
import { currentSessionId } from '@lib/session'

/** Authorized server-side call: refreshes once on a 401 and replays the request exactly once. */
export async function callApi<T>(req: Omit<ApiRequest, 'token'>): Promise<ApiResponse<T>> {
  const sid = await currentSessionId()
  if (!sid) throw new SessionGone()

  const token = await accessTokenFor(sid)
  try {
    return await rawFetch<T>({ ...req, token })
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error
    const refreshed = await refreshAfterUnauthorized(sid)
    return await rawFetch<T>({ ...req, token: refreshed })
  }
}
