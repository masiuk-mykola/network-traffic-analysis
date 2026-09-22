import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from './client'

const { rawFetch } = vi.hoisted(() => ({ rawFetch: vi.fn() }))

vi.mock('./client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./client')>()),
  rawFetch,
}))

const { sessionId } = vi.hoisted(() => ({ sessionId: { current: 'sid-1' } }))

vi.mock('@lib/session', () => ({
  currentSessionId: async () => sessionId.current,
}))

vi.mock('./session-store', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./session-store')>()),
  accessTokenFor: async () => 'token',
  refreshAfterUnauthorized: async () => 'fresh-token',
}))

const { callApi } = await import('./server')

const ok = { status: 200, data: {}, headers: new Headers() }
const refused = (retryAfterMs: number | null) =>
  new ApiError(503, { code: 'unavailable', detail: 'busy' }, retryAfterMs)

let seq = 0

describe('callApi', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    rawFetch.mockReset()
    sessionId.current = `sid-${(seq += 1)}`
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  /** Resolved or rejected, without waiting on a promise that may still be holding. */
  async function settled(promise: Promise<unknown>): Promise<boolean> {
    let done = false
    promise.then(
      () => (done = true),
      () => (done = true),
    )
    await Promise.resolve()
    await Promise.resolve()
    return done
  }

  it('holds a browser read after a render was refused on the same template', async () => {
    // AC-1: the screen is prepared, the API refuses and names three seconds, and the browser asks
    // about a different job a moment later. The server counts that as a retry; it never leaves.
    rawFetch.mockRejectedValueOnce(refused(3_000)).mockResolvedValue(ok)

    await expect(callApi({ path: '/v1/searches/srch_a' })).rejects.toThrow('busy')
    expect(rawFetch).toHaveBeenCalledOnce()

    const next = callApi({ path: '/v1/searches/srch_b' })
    await vi.advanceTimersByTimeAsync(2_900)
    expect(rawFetch).toHaveBeenCalledOnce()

    await vi.advanceTimersByTimeAsync(200)
    await next
    expect(rawFetch).toHaveBeenCalledTimes(2)
  })

  it('holds a render after the browser was refused on the same template', async () => {
    // AC-2: the same pair, the other way round. One memory, so neither side has to know.
    rawFetch.mockRejectedValueOnce(refused(2_000)).mockResolvedValue(ok)

    await expect(callApi({ path: '/v1/me' })).rejects.toThrow('busy')

    const next = callApi({ path: '/v1/me' })
    await vi.advanceTimersByTimeAsync(1_900)
    expect(rawFetch).toHaveBeenCalledOnce()

    await vi.advanceTimersByTimeAsync(200)
    await next
    expect(rawFetch).toHaveBeenCalledTimes(2)
  })

  it('holds a cancellation too, because the window covers every method', async () => {
    // AC-3: the API scores a DELETE inside the window exactly as it scores a GET.
    rawFetch.mockRejectedValueOnce(refused(2_000)).mockResolvedValue(ok)

    await expect(callApi({ path: '/v1/searches/srch_a' })).rejects.toThrow('busy')

    const cancel = callApi({ method: 'DELETE', path: '/v1/searches/srch_a' })
    expect(await settled(cancel)).toBe(false)
    expect(rawFetch).toHaveBeenCalledOnce()

    await vi.advanceTimersByTimeAsync(2_100)
    await cancel
    expect(rawFetch).toHaveBeenCalledTimes(2)
  })

  it('sends at once when the refusal named no delay', async () => {
    // AC-8: nothing about the ordinary case changes.
    rawFetch.mockRejectedValueOnce(refused(null)).mockResolvedValue(ok)

    await expect(callApi({ path: '/v1/me' })).rejects.toThrow('busy')
    await callApi({ path: '/v1/me' })

    expect(rawFetch).toHaveBeenCalledTimes(2)
  })

  it('does not hold a different template', async () => {
    rawFetch.mockRejectedValueOnce(refused(3_000)).mockResolvedValue(ok)

    await expect(callApi({ path: '/v1/searches/srch_a' })).rejects.toThrow('busy')
    await callApi({ path: '/v1/searches/srch_a/results' })

    expect(rawFetch).toHaveBeenCalledTimes(2)
  })

  it('does not hold the refresh a window on another template opened', async () => {
    // Refreshing inside someone else's window would trade a scored retry for a dead session.
    rawFetch.mockRejectedValueOnce(refused(3_000)).mockResolvedValue(ok)
    await expect(callApi({ path: '/v1/me' })).rejects.toThrow('busy')

    await callApi({ method: 'POST', path: '/v1/auth/refresh' })
    expect(rawFetch).toHaveBeenCalledTimes(2)
  })

  it('still refreshes once and replays once on a 401', async () => {
    rawFetch
      .mockRejectedValueOnce(new ApiError(401, { code: 'unauthorized', detail: 'no' }, null))
      .mockResolvedValue(ok)

    await callApi({ path: '/v1/me' })

    expect(rawFetch).toHaveBeenCalledTimes(2)
    expect(rawFetch.mock.calls[1]?.[0]).toMatchObject({ token: 'fresh-token' })
  })

  it('lets a caller that has gone away go, rather than holding its request', async () => {
    rawFetch.mockRejectedValueOnce(refused(3_000)).mockResolvedValue(ok)
    await expect(callApi({ path: '/v1/me' })).rejects.toThrow('busy')

    const abort = new AbortController()
    const held = callApi({ path: '/v1/me', signal: abort.signal })
    const caught = held.catch((error: unknown) => error)
    abort.abort()

    await expect(caught).resolves.toBeInstanceOf(Error)
    expect(rawFetch).toHaveBeenCalledOnce()
  })

  it('does not hold one session because another was refused', async () => {
    rawFetch.mockRejectedValueOnce(refused(3_000)).mockResolvedValue(ok)
    await expect(callApi({ path: '/v1/me' })).rejects.toThrow('busy')

    sessionId.current = 'someone-else'
    await callApi({ path: '/v1/me' })
    expect(rawFetch).toHaveBeenCalledTimes(2)
  })
})
