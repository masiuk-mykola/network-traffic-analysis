import { NextResponse } from 'next/server'

import { toErrorPayload } from '@api/error-response'
import { zListFieldsResponse } from '@api/generated/zod.gen'
import { holdRead } from '@api/hold'
import { callApi } from '@api/server'
import { hasSession, SessionGone } from '@api/session-store'
import { currentSessionId } from '@lib/session'

/**
 * The searchable fields this server publishes.
 *
 * This sits in front of the read proxy for one path, because the catalogue is the same for everyone
 * and changes on the scale of a deploy. The search page already reads it on the server to make sense
 * of a shared link, and seeds the form with it — but when that read is refused the seed is empty and
 * the browser asks for itself. Passed straight through, that second ask is a read the API counts,
 * and a refusal that named a delay becomes a violation of a delay this request never saw.
 *
 * Both readers therefore share one hold, under the key the page uses: it remembers the answer and
 * the read in flight. A refusal that named a delay is waited out underneath, at the seam every
 * call passes through (`@api/advertised-delay`), so it is not this hold's business.
 */
const WINDOW_MS = 60_000
const HOLD_KEY = 'meta/fields'

export async function GET() {
  try {
    // The held answer is behind the same door as every other read: whoever asks needs a session.
    if (!hasSession(await currentSessionId())) throw new SessionGone()

    const body = await holdRead(HOLD_KEY, WINDOW_MS, async () => {
      // No caller's signal here on purpose: another request may be waiting on this same read.
      const { data } = await callApi({ path: '/v1/meta/fields', schema: zListFieldsResponse })
      return data
    })

    return NextResponse.json(body)
  } catch (error) {
    const payload = toErrorPayload(error)
    if (!payload) throw error
    return NextResponse.json(payload.body, { status: payload.status, headers: payload.headers })
  }
}
