import { NextResponse } from 'next/server'

import { toErrorPayload } from '@api/error-response'
import { zGetHealthResponse } from '@api/generated/zod.gen'
import { callApi } from '@api/server'
import { hasSession, SessionGone } from '@api/session-store'
import { currentSessionId } from '@lib/session'

/**
 * Rationed rather than proxied: the API grades the gap between health reads (10 s median), and every
 * tab and mount would ask. One answer is held for everyone, and the read in flight is shared so
 * simultaneous misses do not go upstream in pairs.
 */
const WINDOW_MS = 30_000

type Held = { at: number; body: unknown }

const store = globalThis as typeof globalThis & {
  __captureHealth?: Held
  __captureHealthInFlight?: Promise<unknown>
}

export async function GET() {
  try {
    // A held answer still needs a session.
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
