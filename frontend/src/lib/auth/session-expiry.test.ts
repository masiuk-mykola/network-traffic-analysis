import { describe, expect, it, vi } from 'vitest'

import { HttpError } from '@api/http-error'

import { createExpiryHandler } from './session-expiry'

async function failure(body: Record<string, unknown>, status: number): Promise<HttpError> {
  return HttpError.fromResponse(Response.json(body, { status }))
}

const gone = () => failure({ code: 'session_revoked', detail: 'sign in again' }, 401)

describe('createExpiryHandler', () => {
  it('reacts once, however many requests fail at the same moment', async () => {
    const onExpired = vi.fn()
    const handler = createExpiryHandler({ onExpired })

    const failures = await Promise.all(Array.from({ length: 10 }, gone))
    for (const error of failures) handler.handleFailure(error)

    expect(onExpired).toHaveBeenCalledOnce()
  })

  it('leaves a struggling server alone', async () => {
    const onExpired = vi.fn()
    const handler = createExpiryHandler({ onExpired })

    handler.handleFailure(await failure({ code: 'unavailable', detail: 'busy' }, 503))
    handler.handleFailure(await failure({ code: 'too_many_searches', detail: 'slow' }, 429))
    handler.handleFailure(await failure({ code: 'not_found', detail: 'gone' }, 404))

    expect(onExpired).not.toHaveBeenCalled()
  })

  it('ignores a failure that never reached the API', () => {
    const onExpired = vi.fn()
    const handler = createExpiryHandler({ onExpired })

    handler.handleFailure(new TypeError('network down'))

    expect(onExpired).not.toHaveBeenCalled()
  })

  it('does not react while the app is already at sign in', async () => {
    const onExpired = vi.fn()
    const handler = createExpiryHandler({ onExpired, isSignedOut: () => true })

    handler.handleFailure(await gone())

    expect(onExpired).not.toHaveBeenCalled()
  })

  it('arms again for the next session', async () => {
    const onExpired = vi.fn()
    const handler = createExpiryHandler({ onExpired })

    handler.handleFailure(await gone())
    handler.rearm()
    handler.handleFailure(await gone())

    expect(onExpired).toHaveBeenCalledTimes(2)
  })
})
