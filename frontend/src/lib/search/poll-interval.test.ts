import { describe, expect, it } from 'vitest'

import { MAX_POLL_MS, nextPollDelay, START_POLL_MS } from './poll-interval'

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
