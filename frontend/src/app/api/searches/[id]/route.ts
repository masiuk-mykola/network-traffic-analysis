import { NextResponse } from 'next/server'

import { toErrorPayload } from '@api/error-response'
import { callApi } from '@api/server'

/**
 * Frees the slot: three searches exist per account, and a superseded one is counted against us.
 * Reading a search goes through the read proxy like everything else; this handler exists only for
 * the verb the proxy does not speak.
 */
export async function DELETE(request: Request, ctx: RouteContext<'/api/searches/[id]'>) {
  const { id } = await ctx.params

  try {
    await callApi({
      method: 'DELETE',
      path: `/v1/searches/${encodeURIComponent(id)}`,
      signal: request.signal,
    })
    return new NextResponse(null, { status: 204 })
  } catch (error) {
    return failure(error)
  }
}

function failure(error: unknown): NextResponse {
  const payload = toErrorPayload(error)
  if (!payload) throw error
  return NextResponse.json(payload.body, { status: payload.status, headers: payload.headers })
}
