import { NextResponse } from 'next/server'

import { toErrorPayload } from '@api/error-response'
import { schemaForPath } from '@api/response-schemas'
import { callApi } from '@api/server'

/** The browser calls this instead of the API, which has CORS off and expects a bearer token. */
export async function GET(request: Request, ctx: RouteContext<'/api/capture/[...path]'>) {
  const { path } = await ctx.params
  const query = new URL(request.url).searchParams
  const apiPath = `/v1/${path.join('/')}`

  try {
    const { status, data, headers } = await callApi<unknown>({
      path: apiPath,
      query,
      signal: request.signal,
      schema: schemaForPath(apiPath),
    })
    const limitApplied = headers.get('x-limit-applied')
    return NextResponse.json(data, {
      status,
      headers: limitApplied ? { 'x-limit-applied': limitApplied } : undefined,
    })
  } catch (error) {
    const payload = toErrorPayload(error)
    if (!payload) throw error
    return NextResponse.json(payload.body, { status: payload.status, headers: payload.headers })
  }
}
