import { NextResponse } from 'next/server'

import { callApi } from '@api/server'
import { dropSession, SessionGone } from '@api/session-store'
import { clearSessionCookie, currentSessionId } from '@lib/session'

export async function POST() {
  const sid = await currentSessionId()
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
