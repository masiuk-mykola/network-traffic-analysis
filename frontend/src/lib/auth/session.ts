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
 * The signed-in profile, or a redirect to sign in. Only a missing session or a 401 redirects; any
 * other failure goes to the error boundary rather than throwing a working session away. The cookie
 * is read outside the try: that read marks the route dynamic, and catching it would break that.
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
 * Once per request: the layout's guard and the screen both ask, and `shareProfileRead` only shares a
 * read still in flight — the API counts a repeat after the first has settled.
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
