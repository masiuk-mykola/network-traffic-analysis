import { afterEach, describe, expect, it, vi } from 'vitest'
import * as z from 'zod'

import { parseRetryAfter, rawFetch, SchemaMismatchError } from './client'

const schema = z.object({ id: z.string(), count: z.int() })

function respondWith(body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      Response.json(body, { status: 200, headers: { 'content-type': 'application/json' } }),
    ),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('rawFetch response validation', () => {
  it('returns the body when it matches the schema', async () => {
    vi.stubEnv('CAPTURE_API_URL', 'http://api.test')
    respondWith({ id: '72075232438042624', count: 3 })

    const { data } = await rawFetch({ path: '/v1/thing', schema })

    expect(data).toEqual({ id: '72075232438042624', count: 3 })
  })

  it('rejects a body the schema does not accept', async () => {
    vi.stubEnv('CAPTURE_API_URL', 'http://api.test')
    respondWith({ id: 72075232438042624, count: 'three' })

    await expect(rawFetch({ path: '/v1/thing', schema })).rejects.toBeInstanceOf(
      SchemaMismatchError,
    )
  })

  it('names the offending fields without leaking the body', async () => {
    vi.stubEnv('CAPTURE_API_URL', 'http://api.test')
    respondWith({ id: 1, count: 3 })

    const error = await rawFetch({ path: '/v1/thing', schema }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(SchemaMismatchError)
    expect((error as SchemaMismatchError).issues.join()).toContain('id')
    expect((error as SchemaMismatchError).message).not.toContain('72075')
  })

  it('leaves the body alone when no schema is given', async () => {
    vi.stubEnv('CAPTURE_API_URL', 'http://api.test')
    respondWith({ anything: true })

    const { data } = await rawFetch({ path: '/v1/thing' })

    expect(data).toEqual({ anything: true })
  })
})

describe('parseRetryAfter', () => {
  it('reads seconds', () => {
    expect(parseRetryAfter('5')).toBe(5000)
  })

  it('reads an HTTP-date', () => {
    const now = Date.parse('2026-01-01T00:00:00Z')
    expect(parseRetryAfter('Thu, 01 Jan 2026 00:00:30 GMT', now)).toBe(30_000)
  })

  it('returns null when the header is absent or unusable', () => {
    expect(parseRetryAfter(null)).toBeNull()
    expect(parseRetryAfter('not-a-date')).toBeNull()
  })
})
