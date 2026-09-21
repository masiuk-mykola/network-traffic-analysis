import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, SchemaMismatchError } from './client'
import { toErrorPayload } from './error-response'
import { SessionGone } from './session-store'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('toErrorPayload', () => {
  it('reports a revoked session as 401', () => {
    expect(toErrorPayload(new SessionGone())).toEqual({
      status: 401,
      body: { code: 'session_revoked', detail: 'sign in again' },
    })
  })

  it('hides an upstream contract problem behind a plain 502', () => {
    const logged = vi.spyOn(console, 'error').mockImplementation(() => {})

    const payload = toErrorPayload(
      new SchemaMismatchError('/v1/auth/login', ['id: expected string, received number']),
    )

    expect(payload).toEqual({
      status: 502,
      body: { code: 'upstream_contract', detail: 'unexpected response from the API' },
    })
    expect(JSON.stringify(payload)).not.toContain('expected string')
    expect(logged).toHaveBeenCalledOnce()
  })

  it('passes an API error through with its code', () => {
    const error = new ApiError(404, { code: 'not_found', detail: 'no such session' }, null)

    expect(toErrorPayload(error)).toEqual({
      status: 404,
      body: { code: 'not_found', detail: 'no such session' },
    })
  })

  it('turns an advertised wait into seconds', () => {
    const error = new ApiError(429, { code: 'too_many_searches', detail: 'slow down' }, 4200)

    expect(toErrorPayload(error)?.headers).toEqual({ 'retry-after': '5' })
  })

  it('leaves an unknown failure to the caller', () => {
    expect(toErrorPayload(new Error('boom'))).toBeNull()
  })
})
