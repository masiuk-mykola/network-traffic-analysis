import 'server-only'

import { redirect } from 'next/navigation'
import { cache } from 'react'

import { ApiError } from '@api/client'
import type { components } from '@api/schema'
import { zGetMeResponse } from '@api/generated/zod.gen'
import { callApi } from '@api/server'
import { SessionGone, shareProfileRead } from '@api/session-store'
import { currentSessionId } from '@lib/session'

export type Profile = components['schemas']['Profile']

/**
 * The signed-in profile, or a redirect to sign in. Only a missing session or a refusal from the API
 * counts as "not signed in": anything else — the API being down, a timeout, a contract failure —
 * is rethrown so the error boundary can offer a retry instead of throwing a working session away.
 *
 * The cookie is read outside the try on purpose; reading it is what marks the route dynamic, and
 * swallowing that signal would render every guarded screen as if nobody were signed in.
 */
export async function requireProfile(destination: string): Promise<Profile> {
  const sessionId = await currentSessionId()
  if (!sessionId) redirect(signInUrl(destination))

  try {
    return await readProfile(sessionId)
  } catch (error) {
    if (error instanceof SessionGone) redirect(signInUrl(destination))
    if (error instanceof ApiError && error.status === 401) redirect(signInUrl(destination))
    throw error
  }
}

/**
 * The identity behind a session, read once per request however many server components ask for it.
 *
 * The guard renders in the layout and the screen below it renders in the same pass, so both want
 * the profile: `shareProfileRead` only shares a read still in flight, and the API counts a repeat
 * that arrives after the first has settled.
 */
const readProfile = cache((sessionId: string): Promise<Profile> =>
  shareProfileRead(sessionId, async () => {
    const { data } = await callApi<Profile>({ path: '/v1/me', schema: zGetMeResponse })
    return data
  }),
)

function signInUrl(destination: string): string {
  return `/login?next=${encodeURIComponent(destination)}`
}
