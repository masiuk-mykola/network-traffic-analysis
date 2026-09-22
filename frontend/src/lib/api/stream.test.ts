import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from './client'
import { rawStream } from './stream'

const body = () => new ReadableStream<Uint8Array>({ start: (c) => c.close() })

const ok = () =>
  new Response(body(), { status: 200, headers: { 'content-type': 'text/event-stream' } })

type Call = [url: string, init?: RequestInit]

function stubFetch(answer: Response | (() => Response)) {
  const fetchMock = vi.fn((...call: Call) => {
    void call
    return Promise.resolve(typeof answer === 'function' ? answer() : answer)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('rawStream', () => {
  beforeEach(() => {
    vi.stubEnv('CAPTURE_API_URL', 'http://api.test/')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  const req = () => ({
    path: '/v1/stream/detections',
    token: 't',
    signal: new AbortController().signal,
  })

  it('asks the API for an event stream, with the token on the server side', async () => {
    const fetchMock = stubFetch(ok)

    await rawStream(req())

    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe('http://api.test/v1/stream/detections')
    const headers = init?.headers as Record<string, string>
    expect(headers.accept).toBe('text/event-stream')
    expect(headers.authorization).toBe('Bearer t')
  })

  it('carries a resume point when it is given one', async () => {
    const fetchMock = stubFetch(ok)

    await rawStream({ ...req(), headers: { 'last-event-id': '41' } })

    const [, init] = fetchMock.mock.calls[0] ?? []
    expect((init?.headers as Record<string, string>)['last-event-id']).toBe('41')
  })

  it('appends a query only when there is one', async () => {
    const fetchMock = stubFetch(ok)

    await rawStream({ ...req(), query: new URLSearchParams() })
    await rawStream({ ...req(), query: new URLSearchParams({ sensor_ids: 'hq-core' }) })

    expect(fetchMock.mock.calls[0]?.[0]).toBe('http://api.test/v1/stream/detections')
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      'http://api.test/v1/stream/detections?sensor_ids=hq-core',
    )
  })

  it('hands the caller its own abort signal, and no timeout of its own', async () => {
    // A live feed has no end to read to: `rawFetch`'s fifteen seconds would cut it every time.
    const fetchMock = stubFetch(ok)
    const controller = new AbortController()

    await rawStream({ ...req(), signal: controller.signal })

    const [, init] = fetchMock.mock.calls[0] ?? []
    expect(init?.signal).toBe(controller.signal)
  })

  it('turns a refusal into the same failure as every other call', async () => {
    stubFetch(
      () =>
        new Response(JSON.stringify({ code: 'unavailable', detail: 'busy' }), {
          status: 503,
          headers: { 'content-type': 'application/json', 'retry-after': '2' },
        }),
    )

    const failure = await rawStream(req()).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure).toMatchObject({ status: 503, code: 'unavailable', retryAfterMs: 2_000 })
  })

  it('survives a refusal that is not JSON', async () => {
    stubFetch(
      () => new Response('gateway', { status: 502, headers: { 'content-type': 'text/html' } }),
    )

    const failure = await rawStream(req()).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure).toMatchObject({ status: 502, body: null })
  })

  it('treats an answer with no body as a failure rather than an empty feed', async () => {
    stubFetch(() => new Response(null, { status: 204 }))

    await expect(rawStream(req())).rejects.toBeInstanceOf(ApiError)
  })

  it('refuses to build a URL when the API is not configured', async () => {
    vi.stubEnv('CAPTURE_API_URL', '')
    stubFetch(ok)

    await expect(rawStream(req())).rejects.toThrow('CAPTURE_API_URL')
  })
})
