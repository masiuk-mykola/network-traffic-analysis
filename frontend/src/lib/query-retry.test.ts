import { describe, expect, it } from 'vitest'

import { retry, retryDelay } from '@lib/query-retry'

describe('retry', () => {
  it('does not retry 4xx', () => {
    expect(retry(0, { status: 404, code: 'not_found' })).toBe(false)
  })

  it('retries 429 and 5xx', () => {
    expect(retry(0, { status: 429, code: 'rate_limited' })).toBe(true)
    expect(retry(0, { status: 503, code: 'unavailable' })).toBe(true)
  })

  it('gives up after three attempts', () => {
    expect(retry(3, { status: 503 })).toBe(false)
  })
})

describe('retryDelay', () => {
  it('never comes back sooner than Retry-After', () => {
    expect(retryDelay(0, { status: 429, retryAfterMs: 5000 })).toBe(5000)
  })
})
