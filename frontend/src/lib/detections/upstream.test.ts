import { describe, expect, it, vi } from 'vitest'

import { SessionGone } from '@api/session-store'
import type { SseFrame } from '@api/sse'

const { rawStream } = vi.hoisted(() => ({ rawStream: vi.fn() }))

vi.mock('@api/stream', () => ({ rawStream }))
vi.mock('@api/session-store', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@api/session-store')>()),
  accessTokenFor: async () => 'token',
}))

const { createUpstream, feedFor, stopFeed } = await import('./upstream')
type FeedEvent = import('./upstream').FeedEvent

/** A stream a test can feed frame by frame and end on demand. */
function fakeStream() {
  let push: (frame: SseFrame) => void = () => {}
  let finish: () => void = () => {}
  const queue: SseFrame[] = []
  let waiting: (() => void) | null = null
  let done = false

  async function* frames(): AsyncIterable<SseFrame> {
    for (;;) {
      while (queue.length > 0) yield queue.shift() as SseFrame
      if (done) return
      await new Promise<void>((resolve) => (waiting = resolve))
    }
  }

  push = (frame) => {
    queue.push(frame)
    waiting?.()
    waiting = null
  }
  finish = () => {
    done = true
    waiting?.()
    waiting = null
  }

  return { frames: frames(), push, finish }
}

const frame = (over: Partial<SseFrame> = {}): SseFrame => ({
  comment: null,
  event: null,
  id: null,
  data: '',
  retryMs: null,
  ...over,
})

const detection = (seq: number) =>
  frame({ id: String(seq), event: 'detection', data: JSON.stringify({ seq, id: `d${seq}` }) })

/** Lets the upstream's own promise chain run to its next await. */
const settle = async () => {
  for (let turn = 0; turn < 20; turn += 1) await Promise.resolve()
}

describe('createUpstream', () => {
  it('opens once however many readers attach', async () => {
    const stream = fakeStream()
    const open = vi.fn(async () => stream.frames)
    const upstream = createUpstream({ open, delay: async () => {} })

    upstream.subscribe(() => {})
    upstream.subscribe(() => {})
    await settle()

    expect(open).toHaveBeenCalledOnce()
  })

  it('hands every reader the same detection', async () => {
    const stream = fakeStream()
    const upstream = createUpstream({ open: async () => stream.frames, delay: async () => {} })
    const one: FeedEvent[] = []
    const two: FeedEvent[] = []

    upstream.subscribe((event) => one.push(event))
    upstream.subscribe((event) => two.push(event))
    await settle()
    stream.push(detection(1))
    await settle()

    expect(one.filter((event) => event.kind === 'detection')).toHaveLength(1)
    expect(two.filter((event) => event.kind === 'detection')).toHaveLength(1)
  })

  it('opens with no resume point the first time, and with one after that', async () => {
    const first = fakeStream()
    const second = fakeStream()
    const opens: Array<number | null> = []
    let call = 0
    const upstream = createUpstream({
      open: async ({ resumeFrom }) => {
        opens.push(resumeFrom)
        call += 1
        return call === 1 ? first.frames : second.frames
      },
      delay: async () => {},
    })

    upstream.subscribe(() => {})
    await settle()
    first.push(detection(41))
    await settle()
    first.finish()
    await settle()

    // Every re-open carries a resume point: that is the check the API grades at 95 %.
    expect(opens[0]).toBeNull()
    expect(opens[1]).toBe(41)
  })

  it('resumes from the head the server named, even before any detection arrives', async () => {
    const first = fakeStream()
    const second = fakeStream()
    const opens: Array<number | null> = []
    let call = 0
    const upstream = createUpstream({
      open: async ({ resumeFrom }) => {
        opens.push(resumeFrom)
        call += 1
        return call === 1 ? first.frames : second.frames
      },
      delay: async () => {},
    })

    upstream.subscribe(() => {})
    await settle()
    first.push(frame({ comment: 'open last_seq=12', retryMs: 3_000 }))
    await settle()
    first.finish()
    await settle()

    expect(opens[1]).toBe(12)
  })

  it('waits before re-opening, rather than straight away', async () => {
    const first = fakeStream()
    const waits: number[] = []
    let call = 0
    const upstream = createUpstream({
      open: async () => {
        call += 1
        return call === 1 ? first.frames : fakeStream().frames
      },
      delay: async (ms) => {
        waits.push(ms)
      },
    })

    upstream.subscribe(() => {})
    await settle()
    first.finish()
    await settle()

    expect(waits[0]).toBeGreaterThanOrEqual(1_500)
  })

  it('reports a reset as an ending to explain, and resumes from what it named', async () => {
    const first = fakeStream()
    const second = fakeStream()
    const opens: Array<number | null> = []
    let call = 0
    const events: FeedEvent[] = []
    const upstream = createUpstream({
      open: async ({ resumeFrom }) => {
        opens.push(resumeFrom)
        call += 1
        return call === 1 ? first.frames : second.frames
      },
      delay: async () => {},
    })

    upstream.subscribe((event) => events.push(event))
    await settle()
    first.push(frame({ event: 'reset', data: JSON.stringify({ oldest_seq: 900, last_seq: 1900 }) }))
    await settle()
    first.finish()
    await settle()

    expect(events.some((event) => event.kind === 'reset')).toBe(true)
    expect(opens[1]).toBe(1900)
  })

  it('carries on after a reauth, without the reader doing anything', async () => {
    const first = fakeStream()
    const second = fakeStream()
    let call = 0
    const upstream = createUpstream({
      open: async () => {
        call += 1
        return call === 1 ? first.frames : second.frames
      },
      delay: async () => {},
    })

    upstream.subscribe(() => {})
    await settle()
    first.push(frame({ event: 'reauth', data: JSON.stringify({ reason: 'token_expired' }) }))
    first.finish()
    await settle()

    expect(call).toBe(2)
  })

  it('stops for good when the session is gone, rather than reconnecting into it', async () => {
    // Re-opening after revocation is an authorized request the API counts against us.
    const open = vi.fn(async () => {
      throw new SessionGone()
    })
    const events: FeedEvent[] = []
    const upstream = createUpstream({ open, delay: async () => {} })

    upstream.subscribe((event) => events.push(event))
    await settle()

    expect(open).toHaveBeenCalledOnce()
    expect(events.at(-1)).toEqual({ kind: 'status', status: 'stopped' })
  })

  it('keeps trying after a failure to open', async () => {
    let call = 0
    const upstream = createUpstream({
      open: async () => {
        call += 1
        if (call < 3) throw new Error('refused')
        return fakeStream().frames
      },
      delay: async () => {},
    })

    upstream.subscribe(() => {})
    await settle()

    expect(call).toBeGreaterThanOrEqual(3)
  })

  it('does not close when the last reader leaves, until the grace period passes', async () => {
    const stream = fakeStream()
    const upstream = createUpstream({
      open: async () => stream.frames,
      delay: async () => {},
      graceMs: 10_000,
    })

    const leave = upstream.subscribe(() => {})
    await settle()
    leave()
    await settle()

    // A tab hidden and shown again must not produce a close and an open: that is two graded checks.
    expect(upstream.isRunning()).toBe(true)
  })

  it('closes once the grace period passes with nobody reading', async () => {
    vi.useFakeTimers()
    try {
      const stream = fakeStream()
      const upstream = createUpstream({
        open: async () => stream.frames,
        delay: async () => {},
        graceMs: 10_000,
      })

      const leave = upstream.subscribe(() => {})
      await settle()
      leave()
      await vi.advanceTimersByTimeAsync(10_100)

      expect(upstream.isRunning()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('a reader arriving inside the grace period keeps the stream open', async () => {
    vi.useFakeTimers()
    try {
      const stream = fakeStream()
      const open = vi.fn(async () => stream.frames)
      const upstream = createUpstream({ open, delay: async () => {}, graceMs: 10_000 })

      const leave = upstream.subscribe(() => {})
      await settle()
      leave()
      await vi.advanceTimersByTimeAsync(5_000)
      upstream.subscribe(() => {})
      await vi.advanceTimersByTimeAsync(10_000)

      expect(upstream.isRunning()).toBe(true)
      expect(open).toHaveBeenCalledOnce()
    } finally {
      vi.useRealTimers()
    }
  })

  it('stops on demand and stays stopped', async () => {
    const stream = fakeStream()
    const open = vi.fn(async () => stream.frames)
    const upstream = createUpstream({ open, delay: async () => {} })

    upstream.subscribe(() => {})
    await settle()
    upstream.stop()
    await settle()

    expect(upstream.isRunning()).toBe(false)
    expect(open).toHaveBeenCalledOnce()
  })

  it('tells a reader that attaches late what the connection is doing', async () => {
    const stream = fakeStream()
    const upstream = createUpstream({ open: async () => stream.frames, delay: async () => {} })

    upstream.subscribe(() => {})
    await settle()
    const events: FeedEvent[] = []
    upstream.subscribe((event) => events.push(event))

    expect(events[0]).toEqual({ kind: 'status', status: 'live' })
  })

  it('ignores a detection whose body is not what it claims', async () => {
    const stream = fakeStream()
    const events: FeedEvent[] = []
    const upstream = createUpstream({ open: async () => stream.frames, delay: async () => {} })

    upstream.subscribe((event) => events.push(event))
    await settle()
    stream.push(frame({ id: '5', event: 'detection', data: 'not json' }))
    await settle()

    expect(events.some((event) => event.kind === 'detection')).toBe(false)
  })
})

describe('feedFor', () => {
  it('hands the same feed back for one session, and keeps two sessions apart', () => {
    // One connection per token family is the whole rule: a second feed for the same session would
    // be a second stream the moment anything subscribed to it.
    const first = feedFor('sid-a')

    expect(feedFor('sid-a')).toBe(first)
    expect(feedFor('sid-b')).not.toBe(first)
  })

  it('forgets a feed once it is stopped, so a new session starts clean', () => {
    const first = feedFor('sid-c')
    stopFeed('sid-c')

    expect(feedFor('sid-c')).not.toBe(first)
  })

  it('stopping a feed nobody opened is harmless', () => {
    expect(() => stopFeed('never-opened')).not.toThrow()
  })

  it('opens the upstream feed with the token kept on the server', async () => {
    rawStream.mockResolvedValue({
      status: 200,
      body: streamOf('id: 5\nevent: detection\ndata: {"seq":5}\n\n'),
    })
    const events: FeedEvent[] = []

    const feed = feedFor('sid-d')
    const leave = feed.subscribe((event) => events.push(event))
    await settle()
    await settle()

    const [call] = rawStream.mock.calls[0] as unknown as [Record<string, unknown>]
    expect(call.path).toBe('/v1/stream/detections')
    expect(call.token).toBe('token')
    // Nothing has been seen yet, so the first open carries no resume point.
    expect(call.headers).toEqual({})
    expect(events.some((event) => event.kind === 'detection')).toBe(true)

    leave()
    stopFeed('sid-d')
  })
})

/** A response body carrying the given text, as the API would send it. */
function streamOf(text: string): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text)
  return new ReadableStream({
    start(controller) {
      controller.enqueue(bytes)
      controller.close()
    },
  })
}
