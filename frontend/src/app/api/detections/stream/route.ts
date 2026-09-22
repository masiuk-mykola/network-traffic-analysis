import { toErrorPayload } from '@api/error-response'
import { hasSession, SessionGone } from '@api/session-store'
import { feedFor, type FeedEvent } from '@lib/detections/upstream'
import { currentSessionId } from '@lib/session'
import { NextResponse } from 'next/server'

/**
 * The feed, as this one tab sees it.
 *
 * Every tab gets its own response here, and all of them read from the one upstream connection the
 * session owns. That is the whole point: the API grades opens per token family, so two tabs must
 * not become two streams. A browser reconnecting to *this* endpoint is not a request the API ever
 * sees, so it costs nothing.
 *
 * No `Authorization` is built here. The token stays behind `server-only` in the upstream module,
 * exactly as it does for every other read.
 */
export const dynamic = 'force-dynamic'

const encoder = new TextEncoder()

export async function GET(request: Request) {
  try {
    const sessionId = await currentSessionId()
    if (!hasSession(sessionId) || !sessionId) throw new SessionGone()

    const upstream = feedFor(sessionId)
    let unsubscribe: (() => void) | null = null

    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        let open = true

        const send = (event: FeedEvent) => {
          if (!open) return
          try {
            controller.enqueue(encoder.encode(frame(event)))
          } catch {
            // The tab went away between the check and the write; the abort below cleans up.
            open = false
          }
        }

        unsubscribe = upstream.subscribe(send)

        request.signal.addEventListener(
          'abort',
          () => {
            open = false
            unsubscribe?.()
            unsubscribe = null
            try {
              controller.close()
            } catch {
              // Already closed by the runtime — nothing to undo.
            }
          },
          { once: true },
        )
      },
      cancel() {
        unsubscribe?.()
        unsubscribe = null
      },
    })

    return new Response(body, {
      headers: {
        'content-type': 'text/event-stream; charset=utf-8',
        'cache-control': 'no-store, no-transform',
        connection: 'keep-alive',
      },
    })
  } catch (error) {
    const payload = toErrorPayload(error)
    if (!payload) throw error
    return NextResponse.json(payload.body, { status: payload.status, headers: payload.headers })
  }
}

/** One event, in the wire format the browser's own reader expects. */
function frame(event: FeedEvent): string {
  if (event.kind === 'detection') {
    return `id: ${event.seq}\nevent: detection\ndata: ${JSON.stringify(event.detection)}\n\n`
  }
  if (event.kind === 'reset') {
    const data = JSON.stringify({ oldest_seq: event.oldestSeq, last_seq: event.lastSeq })
    return `event: reset\ndata: ${data}\n\n`
  }
  return `event: status\ndata: ${JSON.stringify({ status: event.status })}\n\n`
}
