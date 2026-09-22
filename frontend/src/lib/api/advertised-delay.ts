import 'server-only'

import { routeTemplate } from './route-template'

/**
 * What the server asked us to wait, remembered where every caller passes.
 *
 * A `429` or `503` carrying `Retry-After` opens a window the API scores against us: any later
 * request on the same route template, of any method, sent before the delay has passed, is counted
 * as a retry. The window belongs to the template and the signed-in session — not to a search, a
 * screen, a hook or a cache entry — so no single caller can honour it. Two attempts at this were
 * made per-caller and both left a third case behind; a memory that lives at the seam instead
 * covers the server render, the read proxy, the write handlers and the replay after a refresh with
 * one rule none of them has to know.
 *
 * It is deliberately a wait rather than a refusal: the delays are one to three seconds, and a
 * cancellation that happens a moment late is better than one that has to be clicked twice.
 *
 * Per-process, like `hold`: a restart forgets, and two instances do not share. That is accepted —
 * what is graded is one reader within one session.
 */
const delays = globalThis as typeof globalThis & { __captureDelays?: Map<string, number> }

function windowKey(sessionId: string, path: string): string {
  // \u0000 cannot occur in either part, so no pair of them can collide with another.
  return `${sessionId}\u0000${routeTemplate(path)}`
}

/** Remember a delay the server named. A refusal that named none changes nothing. */
export function rememberDelay(sessionId: string, path: string, retryAfterMs: number | null): void {
  if (retryAfterMs === null || retryAfterMs <= 0) return

  delays.__captureDelays ??= new Map()
  const key = windowKey(sessionId, path)
  const until = Date.now() + retryAfterMs
  // The longer window wins: a shorter one arriving second would end the wait early.
  const open = delays.__captureDelays.get(key)
  if (open === undefined || until > open) delays.__captureDelays.set(key, until)
}

/**
 * Hold until whatever the server asked for has passed. Resolves at once when nothing was asked.
 * A caller that goes away is let go rather than held: the request it was waiting for is one nobody
 * is listening for any more.
 */
export async function awaitDelay(
  sessionId: string,
  path: string,
  signal?: AbortSignal,
): Promise<void> {
  const key = windowKey(sessionId, path)
  const until = delays.__captureDelays?.get(key)
  if (until === undefined) return

  const remaining = until - Date.now()
  if (remaining <= 0) {
    delays.__captureDelays?.delete(key)
    return
  }

  signal?.throwIfAborted()

  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, remaining)

    function onAbort() {
      clearTimeout(timer)
      reject(signal?.reason ?? new Error('aborted'))
    }

    signal?.addEventListener('abort', onAbort, { once: true })
  })
}
