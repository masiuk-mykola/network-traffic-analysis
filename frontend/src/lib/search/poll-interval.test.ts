import { describe, expect, it } from 'vitest'

import { MAX_POLL_MS, nextPollDelay, pollDelay, START_POLL_MS } from './poll-interval'

describe('nextPollDelay', () => {
  it('starts quick, because a job here can finish in a second', () => {
    expect(nextPollDelay(0)).toBe(START_POLL_MS)
    expect(START_POLL_MS).toBe(500)
  })

  it('doubles as the job goes on', () => {
    expect(nextPollDelay(1)).toBe(1000)
    expect(nextPollDelay(2)).toBe(2000)
    expect(nextPollDelay(3)).toBe(4000)
  })

  it('settles at a ceiling rather than growing forever', () => {
    expect(nextPollDelay(4)).toBe(MAX_POLL_MS)
    expect(nextPollDelay(40)).toBe(MAX_POLL_MS)
    expect(MAX_POLL_MS).toBe(5000)
  })

  it('never asks again immediately, whatever it is given', () => {
    expect(nextPollDelay(-5)).toBe(START_POLL_MS)
    expect(nextPollDelay(Number.NaN)).toBe(START_POLL_MS)
  })
})

describe('pollDelay', () => {
  it('keeps its own cadence when nothing was refused', () => {
    expect(pollDelay(0)).toBe(START_POLL_MS)
    expect(pollDelay(2)).toBe(2000)
    expect(pollDelay(2, { retryAfterMs: null, elapsedMs: 0 })).toBe(2000)
  })

  it('waits out a delay the server advertised, even when its own is shorter', () => {
    // The 503 that asked for two seconds arrived a moment ago; the cadence would ask in half a
    // second, and the API scores that as a retry before the advertised delay.
    expect(pollDelay(0, { retryAfterMs: 2000, elapsedMs: 100 })).toBe(1900)
  })

  it('keeps its own cadence once the advertised delay has already passed', () => {
    expect(pollDelay(3, { retryAfterMs: 2000, elapsedMs: 5000 })).toBe(4000)
  })

  it('ignores a refusal that named no delay', () => {
    expect(pollDelay(1, { retryAfterMs: 0, elapsedMs: 0 })).toBe(1000)
  })
})
