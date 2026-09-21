import { NextResponse } from 'next/server'

import { toErrorPayload } from '@api/error-response'
import { zGetMeResponse } from '@api/generated/zod.gen'
import { callApi } from '@api/server'

/** Who the current session belongs to. A dead session answers 401, never a pretend profile. */
export async function GET(request: Request) {
  try {
    const { data } = await callApi({
      path: '/v1/me',
      signal: request.signal,
      schema: zGetMeResponse,
    })
    return NextResponse.json(data)
  } catch (error) {
    const payload = toErrorPayload(error)
    if (!payload) throw error
    return NextResponse.json(payload.body, { status: payload.status, headers: payload.headers })
  }
}
