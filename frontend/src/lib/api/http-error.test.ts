import { describe, expect, it } from 'vitest'

import { HttpError, isHttpError } from './http-error'

function proxyResponse(body: unknown, init: ResponseInit = {}): Response {
  return Response.json(body, { status: 400, ...init })
}

describe('HttpError.fromResponse', () => {
  it('takes the status, the stable code and the message from the error envelope', async () => {
    const error = await HttpError.fromResponse(
      proxyResponse({ code: 'not_found', detail: 'no such session' }, { status: 404 }),
    )

    expect(error.status).toBe(404)
    expect(error.code).toBe('not_found')
    expect(error.message).toBe('no such session')
  })

  it('keeps the machine-readable extras the envelope carries', async () => {
    const error = await HttpError.fromResponse(
      proxyResponse({ code: 'too_many_searches', detail: 'slow down', slots: 3 }, { status: 429 }),
    )

    expect(error.body).toEqual({ code: 'too_many_searches', detail: 'slow down', slots: 3 })
  })

  it('reads an advertised wait in seconds', async () => {
    const error = await HttpError.fromResponse(
      proxyResponse(
        { code: 'unavailable', detail: 'busy' },
        { status: 503, headers: { 'retry-after': '5' } },
      ),
    )

    expect(error.retryAfterMs).toBe(5000)
  })

  it('reads an advertised wait as an HTTP-date', async () => {
    const at = new Date(Date.now() + 30_000).toUTCString()
    const error = await HttpError.fromResponse(
      proxyResponse(
        { code: 'login_rate_limited', detail: 'wait' },
        { status: 429, headers: { 'retry-after': at } },
      ),
    )

    expect(error.retryAfterMs).toBeGreaterThan(25_000)
    expect(error.retryAfterMs).toBeLessThanOrEqual(30_000)
  })

  it('survives a response that is not the error envelope', async () => {
    const error = await HttpError.fromResponse(new Response('gateway down', { status: 502 }))

    expect(error.status).toBe(502)
    expect(error.code).toBe('http_error')
    expect(error.body).toBeNull()
    expect(error.message).toContain('502')
  })

  it('carries the revoked session as its own code', async () => {
    const error = await HttpError.fromResponse(
      proxyResponse({ code: 'session_revoked', detail: 'sign in again' }, { status: 401 }),
    )

    expect(error.code).toBe('session_revoked')
  })
})

describe('isHttpError', () => {
  it('recognizes its own errors and nothing else', async () => {
    const error = await HttpError.fromResponse(proxyResponse({ code: 'x', detail: 'y' }))

    expect(isHttpError(error)).toBe(true)
    expect(isHttpError(new Error('boom'))).toBe(false)
    expect(isHttpError({ status: 500 })).toBe(false)
  })
})

describe('failure identity', () => {
  it('gives every failure its own id, so a later one is told apart from the one before', async () => {
    const first = await HttpError.fromResponse(proxyResponse({ code: 'x', detail: 'y' }))
    const second = await HttpError.fromResponse(proxyResponse({ code: 'x', detail: 'y' }))

    expect(second.id).not.toBe(first.id)
  })
})
