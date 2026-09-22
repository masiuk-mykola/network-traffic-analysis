import { NextResponse } from 'next/server'

import { toErrorPayload } from '@api/error-response'
import { zListDetectionsResponse } from '@api/generated/zod.gen'
import { holdRead } from '@api/hold'
import { callApi } from '@api/server'
import { hasSession, SessionGone } from '@api/session-store'
import { currentSessionId } from '@lib/session'

/**
 * The detections the server already holds — the feed's seed, and only its seed.
 *
 * This sits in front of the read proxy for one path because a seed read must be shared rather than
 * passed on. Every mount of the feed asks for it, and under load the API answers slowly: a second
 * navigation issues its read before the first one's answer is back, so remembering an advertised
 * delay cannot help — at the moment the second read is sent, nothing here knows the first was
 * refused. Sharing the read in flight is what prevents the pair, which is the same reason the field
 * catalogue and the server's own condition sit here too.
 *
 * The window is short on purpose: what is live arrives on the stream, so this only has to collapse
 * a burst of mounts, not stand in for the feed.
 */
const WINDOW_MS = 5_000
const HOLD_KEY = 'detections'

/** The newest page. The server clamps anything above 500 and reports that it did. */
const SEED_LIMIT = 200

export async function GET() {
  try {
    // The held answer is behind the same door as every other read: whoever asks needs a session.
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
