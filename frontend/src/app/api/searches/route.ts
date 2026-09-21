import { NextResponse } from 'next/server'

import { toErrorPayload } from '@api/error-response'
import { zCreateSearchResponse } from '@api/generated/zod.gen'
import { callApi } from '@api/server'

const IDEMPOTENCY_HEADER = 'idempotency-key'
const REPLAYED_HEADER = 'idempotent-replayed'

/**
 * Starts a search. The browser cannot reach the API, and this is a write, so it gets its own
 * handler rather than the read proxy. The idempotency label comes from the caller and is passed
 * through untouched: it is what makes a retry return the job already started.
 */
export async function POST(request: Request) {
  const label = request.headers.get(IDEMPOTENCY_HEADER)

  try {
    const { status, data, headers } = await callApi({
      method: 'POST',
      path: '/v1/searches',
      body: await request.json(),
      headers: label ? { [IDEMPOTENCY_HEADER]: label } : {},
      schema: zCreateSearchResponse,
      signal: request.signal,
    })

    const replayed = headers.get(REPLAYED_HEADER)
    return NextResponse.json(data, {
      status,
      headers: replayed ? { [REPLAYED_HEADER]: replayed } : undefined,
    })
  } catch (error) {
    const payload = toErrorPayload(error)
    if (!payload) throw error
    return NextResponse.json(payload.body, { status: payload.status, headers: payload.headers })
  }
}
