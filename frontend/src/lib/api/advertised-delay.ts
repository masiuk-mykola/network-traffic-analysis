import 'server-only'

import { routeTemplate } from './route-template'

/**
 * Delays the server named in `Retry-After`, per session and route template. The API counts any
 * request on that template inside the window as a retry, whoever sends it, so no single caller can
 * honour it — the memory lives here, where every server call passes. Per-process, like `hold`.
 */
const delays = globalThis as typeof globalThis & { __captureDelays?: Map<string, number> }

function windowKey(sessionId: string, path: string): string {
  // \u0000 cannot occur in either part, so no pair of them can collide with another.
  return `${sessionId}\u0000${routeTemplate(path)}`
}

export function rememberDelay(sessionId: string, path: string, retryAfterMs: number | null): void {
  if (retryAfterMs === null || retryAfterMs <= 0) return

  delays.__captureDelays ??= new Map()
  const key = windowKey(sessionId, path)
  const until = Date.now() + retryAfterMs
  // The longer window wins: a shorter one arriving second would end the wait early.
  const open = delays.__captureDelays.get(key)
  if (open === undefined || until > open) delays.__captureDelays.set(key, until)
}

/** A wait rather than a refusal: the delays are a few seconds. An aborted caller is let go. */
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
