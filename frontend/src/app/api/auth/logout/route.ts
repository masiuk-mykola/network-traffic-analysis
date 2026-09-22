import { NextResponse } from 'next/server'

import { callApi } from '@api/server'
import { dropSession, SessionGone } from '@api/session-store'
import { stopFeed } from '@lib/detections/upstream'
import { clearSessionCookie, currentSessionId } from '@lib/session'

export async function POST() {
  const sid = await currentSessionId()
  // Before anything else: a stream still open when the family is revoked is an authorized request
  // the API counts, and it would try to re-open into a session that no longer exists.
  if (sid) stopFeed(sid)
  try {
    await callApi({ method: 'POST', path: '/v1/auth/logout' })
  } catch (error) {
    // An already-dead session is a successful logout too.
    if (!(error instanceof SessionGone)) throw error
  } finally {
    if (sid) dropSession(sid)
    await clearSessionCookie()
  }
  return new NextResponse(null, { status: 204 })
}
