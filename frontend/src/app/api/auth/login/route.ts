import { NextResponse } from 'next/server'

import { ApiError, rawFetch, type TokenPair } from '@api/client'
import { putSession } from '@api/session-store'
import { newSessionId, setSessionCookie } from '@lib/session'

export async function POST(request: Request) {
  const { email, password } = (await request.json()) as { email?: string; password?: string }
  if (!email || !password) {
    return NextResponse.json(
      { code: 'bad_request', detail: 'email and password required' },
      { status: 400 },
    )
  }

  try {
    const { data } = await rawFetch<TokenPair>({
      method: 'POST',
      path: '/v1/auth/login',
      body: { email, password },
    })
    const sid = newSessionId()
    putSession(sid, data)
    await setSessionCookie(sid)
    // Only the profile goes out; the tokens stay on the server.
    return NextResponse.json({ user: data.user })
  } catch (error) {
    if (error instanceof ApiError) {
      const headers =
        error.retryAfterMs === null
          ? undefined
          : { 'retry-after': String(Math.ceil(error.retryAfterMs / 1000)) }
      return NextResponse.json(error.body ?? { code: error.code, detail: error.message }, {
        status: error.status,
        headers,
      })
    }
    throw error
  }
}
