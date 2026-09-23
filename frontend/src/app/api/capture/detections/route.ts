import { NextResponse } from 'next/server'

import { toErrorPayload } from '@api/error-response'
import { zListDetectionsResponse } from '@api/generated/zod.gen'
import { holdRead } from '@api/hold'
import { callApi } from '@api/server'
import { hasSession, SessionGone } from '@api/session-store'
import { currentSessionId } from '@lib/session'

/**
 * The feed's seed, shared rather than proxied: a burst of mounts would otherwise send the same read
 * before the first answer (or refusal) is back. The window is short because what is live arrives on
 * the stream.
 */
const WINDOW_MS = 5_000
const HOLD_KEY = 'detections'
const SEED_LIMIT = 200

export async function GET() {
  try {
    if (!hasSession(await currentSessionId())) throw new SessionGone()

    const body = await holdRead(HOLD_KEY, WINDOW_MS, async () => {
      // No caller's signal here on purpose: another request may be waiting on this same read.
      const { data } = await callApi({
        path: '/v1/detections',
        query: new URLSearchParams({ limit: String(SEED_LIMIT) }),
        schema: zListDetectionsResponse,
      })
      return data
    })

    return NextResponse.json(body)
  } catch (error) {
    const payload = toErrorPayload(error)
    if (!payload) throw error
    return NextResponse.json(payload.body, { status: payload.status, headers: payload.headers })
  }
}
