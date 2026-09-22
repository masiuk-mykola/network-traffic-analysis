import 'server-only'

import { ApiError } from '@api/client'
import { accessTokenFor, SessionGone } from '@api/session-store'
import { parseSse, type SseFrame } from '@api/sse'
import { rawStream } from '@api/stream'

import { reconnectDelay, type EndReason } from './reconnect'
import type { FeedEvent, FeedStatus } from './upstream-events'

export type { FeedEvent, FeedStatus }

/**
 * One live feed per signed-in session, on the server.
 *
 * The API grades this per token family: no two opens within a second, no open within a second of a
 * close, and at least 95 % of re-opens carrying a resume point. Two browser tabs are one family, so
 * a connection owned by the browser would fail the first of those the moment a second tab appeared.
 * The connection therefore lives here, once, and every tab reads from it through our own endpoint —
 * which the API never sees.
 *
 * Per-process, like `@api/hold` and `@api/advertised-delay`, and for the same reasons: a module
 * reload must not lose it, a restart may forget it, and two app instances do not share one.
 */
type Reader = (event: FeedEvent) => void

export type OpenInput = { resumeFrom: number | null; signal: AbortSignal }

export type UpstreamDeps = {
  open: (input: OpenInput) => Promise<AsyncIterable<SseFrame>>
  delay: (ms: number, signal: AbortSignal) => Promise<void>
  /** How long the connection is held after the last reader leaves. */
  graceMs?: number
}

export type Upstream = {
  subscribe: (reader: Reader) => () => void
  stop: () => void
  isRunning: () => boolean
}

/**
 * Holding the connection after the last reader leaves is deliberate. A tab hidden and shown again
 * would otherwise produce a close and an open, which is precisely what two of the three graded
 * checks measure. One idle connection for half a minute is the cheaper mistake.
 */
const DEFAULT_GRACE_MS = 30_000

export function createUpstream(deps: UpstreamDeps): Upstream {
  const graceMs = deps.graceMs ?? DEFAULT_GRACE_MS
  const readers = new Set<Reader>()

  let status: FeedStatus = 'reconnecting'
  let resumeFrom: number | null = null
  let hintMs: number | undefined
  let failures = 0
  let stopped = false
  let running = false
  let abort: AbortController | null = null
  let graceTimer: ReturnType<typeof setTimeout> | null = null

  function announce(event: FeedEvent) {
    for (const reader of readers) reader(event)
  }

  function setStatus(next: FeedStatus) {
    if (status === next) return
    status = next
    announce({ kind: 'status', status: next })
  }

  function stop() {
    stopped = true
    running = false
    if (graceTimer) clearTimeout(graceTimer)
    graceTimer = null
    abort?.abort()
    abort = null
    setStatus('stopped')
  }

  function handle(frame: SseFrame): EndReason | null {
    if (frame.retryMs !== null) hintMs = frame.retryMs
    // The opening comment names the head of the feed, so a re-open can resume from it even when no
    // detection has arrived yet.
    const head = frame.comment?.match(/last_seq=(\d+)/)?.[1]
    if (head !== undefined && resumeFrom === null) resumeFrom = Number(head)

    if (frame.event === 'reauth') return 'reauth'
    if (frame.event === 'reset') {
      const body = readJson(frame.data)
      const lastSeq = readNumber(body, 'last_seq')
      const oldestSeq = readNumber(body, 'oldest_seq')
      if (lastSeq === null || oldestSeq === null) return null
      resumeFrom = lastSeq
      announce({ kind: 'reset', oldestSeq, lastSeq })
      return null
    }
    if (frame.event !== 'detection') return null

    const body = readJson(frame.data)
    const seq = readNumber(body, 'seq') ?? Number(frame.id)
    if (body === null || !Number.isFinite(seq)) return null

    resumeFrom = resumeFrom === null ? seq : Math.max(resumeFrom, seq)
    announce({ kind: 'detection', seq, detection: body })
    return null
  }

  async function run() {
    running = true
    while (!stopped) {
      const controller = new AbortController()
      abort = controller
      let reason: EndReason = 'rotate'

      try {
        const frames = await deps.open({ resumeFrom, signal: controller.signal })
        failures = 0
        setStatus('live')
        for await (const frame of frames) {
          const ending = handle(frame)
          if (ending) {
            reason = ending
            break
          }
        }
      } catch (error) {
        // A session that is gone is an ending, not a setback: re-opening into a revoked family is
        // an authorized request the API counts against us.
        if (isSessionGone(error)) {
          stop()
          return
        }
        failures += 1
        reason = 'error'
      }

      if (stopped) break
      setStatus('reconnecting')
      await deps.delay(reconnectDelay({ reason, failures, hintMs }), controller.signal)
    }
    running = false
  }

  function closeAfterGrace() {
    if (graceTimer || stopped) return
    graceTimer = setTimeout(() => {
      graceTimer = null
      if (readers.size === 0) stop()
    }, graceMs)
  }

  return {
    subscribe(reader) {
      readers.add(reader)
      if (graceTimer) {
        clearTimeout(graceTimer)
        graceTimer = null
      }
      // A reader arriving mid-flight needs to know what it arrived into.
      reader({ kind: 'status', status })
      if (!running && !stopped) void run()

      return () => {
        readers.delete(reader)
        if (readers.size === 0) closeAfterGrace()
      }
    },
    stop,
    isRunning: () => running && !stopped,
  }
}

function readJson(data: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(data)
    return typeof parsed === 'object' && parsed !== null
      ? (parsed as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}

function readNumber(body: Record<string, unknown> | null, key: string): number | null {
  const value = body?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function isSessionGone(error: unknown): boolean {
  if (error instanceof SessionGone) return true
  return error instanceof ApiError && (error.status === 401 || error.status === 403)
}

/* ------------------------------------------------------------------ the live one, per session */

const feeds = globalThis as typeof globalThis & { __captureFeeds?: Map<string, Upstream> }

const STREAM_PATH = '/v1/stream/detections'

export function feedFor(sessionId: string): Upstream {
  feeds.__captureFeeds ??= new Map()
  const existing = feeds.__captureFeeds.get(sessionId)
  if (existing) return existing

  const upstream = createUpstream({
    open: async ({ resumeFrom, signal }) => {
      // Taken fresh on every open, so a stream that ended with `reauth` comes back under a live
      // token. The store refreshes single-flight, so several opens cannot burn a refresh token.
      const token = await accessTokenFor(sessionId)
      const { body } = await rawStream({
        path: STREAM_PATH,
        token,
        signal,
        headers: resumeFrom === null ? {} : { 'last-event-id': String(resumeFrom) },
      })
      return framesOf(body)
    },
    delay: wait,
  })

  feeds.__captureFeeds.set(sessionId, upstream)
  return upstream
}

/** Ends the feed for a session and forgets it, so nothing reconnects into a revoked family. */
export function stopFeed(sessionId: string): void {
  const upstream = feeds.__captureFeeds?.get(sessionId)
  if (!upstream) return
  upstream.stop()
  feeds.__captureFeeds?.delete(sessionId)
}

async function* framesOf(body: ReadableStream<Uint8Array>): AsyncIterable<SseFrame> {
  const parser = parseSse()
  const reader = body.getReader()
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      if (value) yield* parser.push(value)
    }
    yield* parser.end()
  } finally {
    reader.releaseLock()
  }
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    function onAbort() {
      clearTimeout(timer)
      resolve()
    }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}
