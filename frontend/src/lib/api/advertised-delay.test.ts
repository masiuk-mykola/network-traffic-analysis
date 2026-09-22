import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { awaitDelay, rememberDelay } from './advertised-delay'

// The store lives on `globalThis` and has no reset, like `hold`'s: each case uses its own session.
let seq = 0
const session = () => `s${(seq += 1)}`

describe('advertised delay', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  /** Resolved, still pending, or rejected — without waiting on a promise that may never settle. */
  async function settled(promise: Promise<unknown>): Promise<boolean> {
    let done = false
    promise.then(
      () => (done = true),
      () => (done = true),
    )
    await Promise.resolve()
    return done
  }

  it('waits out the remainder on a different path of the same template', async () => {
    // The API opens its window on the route template, not the id: a refusal on one job silences
    // every later request about any job, which is the whole reason this lives here and not in a
    // hook. Anything less is a violation the client cannot see.
    const sid = session()
    rememberDelay(sid, '/v1/searches/srch_a', 2_000)

    const waiting = awaitDelay(sid, '/v1/searches/srch_b')
    expect(await settled(waiting)).toBe(false)

    await vi.advanceTimersByTimeAsync(1_999)
    expect(await settled(waiting)).toBe(false)

    await vi.advanceTimersByTimeAsync(2)
    expect(await settled(waiting)).toBe(true)
  })

  it('keeps a nested template on its own window', async () => {
    const sid = session()
    rememberDelay(sid, '/v1/searches/srch_a', 5_000)

    await expect(awaitDelay(sid, '/v1/searches/srch_a/results')).resolves.toBeUndefined()
  })

  it('sends at once when the refusal named no delay', async () => {
    const sid = session()
    rememberDelay(sid, '/v1/searches/srch_a', null)
    rememberDelay(sid, '/v1/searches/srch_a', 0)

    await expect(awaitDelay(sid, '/v1/searches/srch_a')).resolves.toBeUndefined()
  })

  it('sends at once once the delay has passed', async () => {
    const sid = session()
    rememberDelay(sid, '/v1/me', 1_000)
    await vi.advanceTimersByTimeAsync(1_000)

    await expect(awaitDelay(sid, '/v1/me')).resolves.toBeUndefined()
  })

  it('keeps the longer of two delays on the same template', async () => {
    const sid = session()
    rememberDelay(sid, '/v1/me', 3_000)
    rememberDelay(sid, '/v1/me', 1_000)

    const waiting = awaitDelay(sid, '/v1/me')
    await vi.advanceTimersByTimeAsync(1_500)
    expect(await settled(waiting)).toBe(false)

    await vi.advanceTimersByTimeAsync(1_600)
    expect(await settled(waiting)).toBe(true)
  })

  it('does not delay one session because another was refused', async () => {
    // The API scores per token family. Two accounts against one dev server are two families.
    const refused = session()
    rememberDelay(refused, '/v1/me', 3_000)

    await expect(awaitDelay(session(), '/v1/me')).resolves.toBeUndefined()
  })

  it('does not delay a different template', async () => {
    const sid = session()
    rememberDelay(sid, '/v1/searches/srch_a', 3_000)

    await expect(awaitDelay(sid, '/v1/auth/refresh')).resolves.toBeUndefined()
  })

  it('gives up when the caller goes away, rather than holding a request nobody wants', async () => {
    const sid = session()
    rememberDelay(sid, '/v1/me', 3_000)
    const abort = new AbortController()

    const waiting = awaitDelay(sid, '/v1/me', abort.signal)
    const caught = waiting.catch((error: unknown) => error)
    abort.abort()

    await expect(caught).resolves.toBeInstanceOf(Error)
  })

  it('gives up at once when the caller has already gone away', async () => {
    const sid = session()
    rememberDelay(sid, '/v1/me', 3_000)

    await expect(awaitDelay(sid, '/v1/me', AbortSignal.abort())).rejects.toThrow()
  })

  it('treats a path the document does not describe as its own window', async () => {
    const sid = session()
    rememberDelay(sid, '/v1/not/a/known/path', 3_000)

    await expect(awaitDelay(sid, '/v1/me')).resolves.toBeUndefined()
    expect(await settled(awaitDelay(sid, '/v1/not/a/known/path'))).toBe(false)
  })
})
