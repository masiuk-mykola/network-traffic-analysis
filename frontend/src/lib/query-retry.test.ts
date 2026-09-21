import { describe, expect, it } from 'vitest'

import { HttpError } from '@api/http-error'
import { retry, retryDelay } from '@lib/query-retry'

async function httpError(body: Record<string, unknown>, init: ResponseInit): Promise<HttpError> {
  return HttpError.fromResponse(Response.json(body, init))
}

describe('retry', () => {
  it('does not retry 4xx', async () => {
    expect(retry(0, await httpError({ code: 'not_found' }, { status: 404 }))).toBe(false)
  })

  it('retries 429 and 5xx', async () => {
    expect(retry(0, await httpError({ code: 'rate_limited' }, { status: 429 }))).toBe(true)
    expect(retry(0, await httpError({ code: 'unavailable' }, { status: 503 }))).toBe(true)
  })

  it('gives up after three attempts', async () => {
    expect(retry(3, await httpError({ code: 'unavailable' }, { status: 503 }))).toBe(false)
  })

  it('never retries a revoked session, whatever the status says', async () => {
    const revoked = await httpError({ code: 'session_revoked' }, { status: 503 })

    expect(retry(0, revoked)).toBe(false)
  })
})

describe('retryDelay', () => {
  it('never comes back sooner than Retry-After', async () => {
    const limited = await httpError(
      { code: 'too_many_searches' },
      { status: 429, headers: { 'retry-after': '5' } },
    )

    expect(retryDelay(0, limited)).toBe(5000)
  })

  it('backs off on its own when the server advertised nothing', async () => {
    const failed = await httpError({ code: 'unavailable' }, { status: 503 })

    expect(retryDelay(0, failed)).toBe(1000)
    expect(retryDelay(3, failed)).toBe(8000)
  })
})
