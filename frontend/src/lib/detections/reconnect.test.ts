import { describe, expect, it } from 'vitest'

import { MAX_RECONNECT_MS, MIN_RECONNECT_MS, reconnectDelay, SERVER_HINT_MS } from './reconnect'

describe('reconnectDelay', () => {
  it('never re-opens sooner than the server tolerates', () => {
    // The API fails us for opening within a second of a close. The floor sits above that, not on it.
    expect(MIN_RECONNECT_MS).toBeGreaterThan(1_000)
    expect(reconnectDelay({ reason: 'rotate', failures: 0 })).toBeGreaterThanOrEqual(
      MIN_RECONNECT_MS,
    )
  })

  it('takes the hint the server sent when it opened the stream', () => {
    expect(reconnectDelay({ reason: 'rotate', failures: 0 })).toBe(SERVER_HINT_MS)
    expect(SERVER_HINT_MS).toBe(3_000)
  })

  it('treats a rotation and a reauth as endings, not as failures', () => {
    // Both are the server working as designed: wait the ordinary pause and come back.
    expect(reconnectDelay({ reason: 'reauth', failures: 0 })).toBe(SERVER_HINT_MS)
    expect(reconnectDelay({ reason: 'reset', failures: 0 })).toBe(SERVER_HINT_MS)
  })

  it('lengthens the wait when opening keeps failing', () => {
    const first = reconnectDelay({ reason: 'error', failures: 1 })
    const second = reconnectDelay({ reason: 'error', failures: 2 })
    const third = reconnectDelay({ reason: 'error', failures: 3 })

    expect(second).toBeGreaterThan(first)
    expect(third).toBeGreaterThan(second)
  })

  it('settles at a ceiling rather than growing forever', () => {
    expect(reconnectDelay({ reason: 'error', failures: 40 })).toBe(MAX_RECONNECT_MS)
    expect(MAX_RECONNECT_MS).toBe(30_000)
  })

  it('goes back to the ordinary pause once an open succeeds', () => {
    // The caller resets its failure count on a successful open; the policy must honour that.
    expect(reconnectDelay({ reason: 'rotate', failures: 0 })).toBe(SERVER_HINT_MS)
  })

  it('honours a longer hint the server sent, and ignores a shorter one', () => {
    expect(reconnectDelay({ reason: 'rotate', failures: 0, hintMs: 10_000 })).toBe(10_000)
    expect(reconnectDelay({ reason: 'rotate', failures: 0, hintMs: 100 })).toBe(SERVER_HINT_MS)
  })

  it('never returns something that is not a usable wait', () => {
    for (const failures of [-1, 0, Number.NaN, Number.POSITIVE_INFINITY]) {
      const delay = reconnectDelay({ reason: 'error', failures })
      expect(Number.isFinite(delay)).toBe(true)
      expect(delay).toBeGreaterThanOrEqual(MIN_RECONNECT_MS)
    }
  })
})
