import { NextResponse } from 'next/server'

import { rawFetch, type TokenPair } from '@api/client'
import { toErrorPayload } from '@api/error-response'
import { zLoginResponse } from '@api/generated/zod.gen'
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
      schema: zLoginResponse,
    })
    const sid = newSessionId()
    putSession(sid, data)
    await setSessionCookie(sid)
    // Only the profile goes out; the tokens stay on the server.
    return NextResponse.json({ user: data.user })
  } catch (error) {
    const payload = toErrorPayload(error)
    if (!payload) throw error
    return NextResponse.json(payload.body, { status: payload.status, headers: payload.headers })
  }
}
