import { NextResponse } from 'next/server'

import { ApiError } from '@api/client'
import { callApi } from '@api/server'
import { SessionGone } from '@api/session-store'

/** The browser calls this instead of the API, which has CORS off and expects a bearer token. */
export async function GET(request: Request, ctx: RouteContext<'/api/capture/[...path]'>) {
  const { path } = await ctx.params
  const query = new URL(request.url).searchParams

  try {
    const { status, data, headers } = await callApi<unknown>({
      path: `/v1/${path.join('/')}`,
      query,
      signal: request.signal,
    })
    const limitApplied = headers.get('x-limit-applied')
    return NextResponse.json(data, {
      status,
      headers: limitApplied ? { 'x-limit-applied': limitApplied } : undefined,
    })
  } catch (error) {
    return errorResponse(error)
  }
}

function errorResponse(error: unknown): NextResponse {
  if (error instanceof SessionGone) {
    return NextResponse.json({ code: 'session_revoked', detail: 'sign in again' }, { status: 401 })
  }
  if (error instanceof ApiError) {
    return NextResponse.json(error.body ?? { code: error.code, detail: error.message }, {
      status: error.status,
      headers:
        error.retryAfterMs === null
          ? undefined
          : { 'retry-after': String(Math.ceil(error.retryAfterMs / 1000)) },
    })
  }
  throw error
}
