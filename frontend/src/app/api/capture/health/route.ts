import { NextResponse } from 'next/server'

import { toErrorPayload } from '@api/error-response'
import { zGetHealthResponse } from '@api/generated/zod.gen'
import { callApi } from '@api/server'
import { hasSession, SessionGone } from '@api/session-store'
import { currentSessionId } from '@lib/session'

/**
 * How the server says it is.
 *
 * This sits in front of the read proxy for one path, because this read must be rationed rather than
 * passed on: the API grades the median gap between health reads at ten seconds, and every tab, every
 * navigation and every mount would otherwise ask again. The answer is the same for everyone, so one
 * answer is kept here and handed out until it goes stale.
 *
 * Rationing a result is not enough on its own: several screens asking at once would all miss an
 * empty cache and all go upstream, which is how a "cached" read still arrives at the API in pairs.
 * The read in flight is therefore shared, exactly as the profile read is.
 */
const WINDOW_MS = 30_000

type Held = { at: number; body: unknown }

const store = globalThis as typeof globalThis & {
  __captureHealth?: Held
  __captureHealthInFlight?: Promise<unknown>
}

export async function GET() {
  try {
    // The held answer is behind the same door as every other read: whoever asks needs a session,
    // even when the answer is already in hand.
    if (!hasSession(await currentSessionId())) throw new SessionGone()

    const held = store.__captureHealth
    if (held && Date.now() - held.at < WINDOW_MS) {
      return NextResponse.json(held.body, { headers: { 'x-capture-health': 'held' } })
    }

    const body = await read()
    return NextResponse.json(body)
  } catch (error) {
    const payload = toErrorPayload(error)
    if (!payload) throw error
    return NextResponse.json(payload.body, { status: payload.status, headers: payload.headers })
  }
}

/** One read at a time, whatever asks: the second caller waits for the first one's answer. */
function read(): Promise<unknown> {
  store.__captureHealthInFlight ??= callApi({
    path: '/v1/health',
    // No caller's signal here on purpose: another request may be waiting on this same read.
    schema: zGetHealthResponse,
  })
    .then(({ data }) => {
      store.__captureHealth = { at: Date.now(), body: data }
      return data
    })
    .finally(() => {
      store.__captureHealthInFlight = undefined
    })

  return store.__captureHealthInFlight
}
