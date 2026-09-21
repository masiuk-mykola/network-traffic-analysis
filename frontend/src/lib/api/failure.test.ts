import { describe, expect, it } from 'vitest'

import { describeFailure } from './failure'
import { HttpError } from './http-error'

async function failure(body: Record<string, unknown>, init: ResponseInit) {
  return describeFailure(await HttpError.fromResponse(Response.json(body, init)))
}

describe('describeFailure', () => {
  it('ends the session without offering a retry', async () => {
    const shown = await failure(
      { code: 'session_revoked', detail: 'sign in again' },
      { status: 401 },
    )

    expect(shown.retryable).toBe(false)
    expect(shown.title).toMatch(/session/i)
  })

  it('does not offer a retry for something the user may not see', async () => {
    const shown = await failure({ code: 'forbidden', detail: 'observer' }, { status: 403 })

    expect(shown.retryable).toBe(false)
  })

  it('does not offer a retry for something that is not there', async () => {
    const shown = await failure(
      { code: 'session_not_found', detail: 'no such session' },
      { status: 404 },
    )

    expect(shown.retryable).toBe(false)
  })

  it('carries the wait the server asked for', async () => {
    const shown = await failure(
      { code: 'too_many_searches', detail: 'slow down' },
      { status: 429, headers: { 'retry-after': '5' } },
    )

    expect(shown.retryable).toBe(true)
    expect(shown.retryAfterMs).toBe(5000)
  })

  it('keeps our own contract failure generic', async () => {
    const shown = await failure(
      { code: 'upstream_contract', detail: 'unexpected response from the API' },
      { status: 502 },
    )

    expect(shown.retryable).toBe(true)
    expect(`${shown.title} ${shown.detail}`).not.toMatch(/schema|expected|zod/i)
  })

  it('retries a server failure', async () => {
    const shown = await failure({ code: 'unavailable', detail: 'busy' }, { status: 503 })

    expect(shown.retryable).toBe(true)
  })

  it('uses the API wording for a request the server rejected', async () => {
    const shown = await failure(
      { code: 'bad_filter', detail: 'unknown field: foo' },
      { status: 400 },
    )

    expect(shown.retryable).toBe(false)
    expect(shown.detail).toBe('unknown field: foo')
  })

  it('shows the stable code so it can be quoted in a report', async () => {
    const shown = await failure({ code: 'invalid_cursor', detail: 'bad cursor' }, { status: 400 })

    expect(shown.code).toBe('invalid_cursor')
  })

  it('handles a failure that never reached the API', () => {
    const shown = describeFailure(new TypeError('network down'))

    expect(shown.retryable).toBe(true)
    expect(shown.code).toBeNull()
  })
})
