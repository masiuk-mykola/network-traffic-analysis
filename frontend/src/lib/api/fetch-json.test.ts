import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchJson } from './fetch-json'
import { HttpError } from './http-error'

function stubFetch(response: Response) {
  const spy = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response)
  vi.stubGlobal('fetch', spy)
  return spy
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchJson', () => {
  it('returns the parsed body', async () => {
    stubFetch(Response.json({ items: [] }, { status: 200 }))

    await expect(fetchJson('sensors')).resolves.toEqual({ items: [] })
  })

  it('goes through our own proxy, never the API', async () => {
    const spy = stubFetch(Response.json({}, { status: 200 }))

    await fetchJson('sessions/72075232438042624')

    expect(String(spy.mock.calls[0]?.[0])).toBe('/api/capture/sessions/72075232438042624')
  })

  it('appends the query it was given', async () => {
    const spy = stubFetch(Response.json({}, { status: 200 }))

    await fetchJson('searches/7/results', { query: new URLSearchParams({ limit: '500' }) })

    expect(String(spy.mock.calls[0]?.[0])).toBe('/api/capture/searches/7/results?limit=500')
  })

  it('sends no credentials of its own', async () => {
    const spy = stubFetch(Response.json({}, { status: 200 }))

    await fetchJson('me')

    const headers = new Headers(spy.mock.calls[0]?.[1]?.headers)
    expect(headers.get('authorization')).toBeNull()
    expect(headers.get('accept')).toBe('application/json')
  })

  it('forwards the caller signal, so cancelling a query cancels the request', async () => {
    const spy = stubFetch(Response.json({}, { status: 200 }))
    const controller = new AbortController()

    await fetchJson('me', { signal: controller.signal })

    expect(spy.mock.calls[0]?.[1]?.signal).toBe(controller.signal)
  })

  it('throws a typed failure carrying the API code', async () => {
    stubFetch(Response.json({ code: 'not_found', detail: 'no such session' }, { status: 404 }))

    const error = await fetchJson('sessions/1').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(HttpError)
    expect((error as HttpError).code).toBe('not_found')
    expect((error as HttpError).status).toBe(404)
  })

  it('throws on a revoked session too, with its own code', async () => {
    stubFetch(Response.json({ code: 'session_revoked', detail: 'sign in again' }, { status: 401 }))

    const error = await fetchJson('me').catch((e: unknown) => e)

    expect((error as HttpError).code).toBe('session_revoked')
  })
})
