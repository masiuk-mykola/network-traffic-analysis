import 'server-only'

import { ApiError, type ErrorBody } from './client'
import { parseRetryAfter } from './retry-after'

/**
 * One authorized streaming GET, beside `rawFetch` rather than inside it.
 *
 * `rawFetch` reads a body to completion and gives every call a fifteen-second timeout. Both are
 * exactly wrong here: a live feed has no end to read to, and a timeout would cut it a quarter of a
 * minute in. So this opens the response and hands the body back for the caller to own.
 *
 * It also does not go through `callApi`. A stream is not a request that can be replayed after a
 * refresh — by the time a token expires the response has long since started — so a dead token is
 * handled by re-opening under the reconnect policy instead, in `@lib/detections/upstream`.
 */
const BASE_URL_MISSING = 'CAPTURE_API_URL is not set'

export type StreamResponse = {
  status: number
  body: ReadableStream<Uint8Array>
}

export type StreamRequest = {
  path: string
  query?: URLSearchParams
  token: string
  headers?: Record<string, string>
  signal: AbortSignal
}

export async function rawStream(req: StreamRequest): Promise<StreamResponse> {
  const { path, query, token, headers = {}, signal } = req
  const url = `${baseUrl()}${path}${query && [...query].length > 0 ? `?${query}` : ''}`

  const res = await fetch(url, {
    method: 'GET',
    signal,
    cache: 'no-store',
    headers: {
      accept: 'text/event-stream',
      authorization: `Bearer ${token}`,
      ...headers,
    },
  })

  if (!res.ok) {
    const problem = await readProblem(res)
    throw new ApiError(res.status, problem, parseRetryAfter(res.headers.get('retry-after')))
  }
  if (!res.body) throw new ApiError(res.status, null, null)

  return { status: res.status, body: res.body }
}

function baseUrl(): string {
  const url = process.env.CAPTURE_API_URL
  if (!url) throw new Error(BASE_URL_MISSING)
  return url.replace(/\/+$/, '')
}

async function readProblem(res: Response): Promise<ErrorBody | null> {
  if (!(res.headers.get('content-type') ?? '').includes('json')) return null
  try {
    return (await res.json()) as ErrorBody
  } catch {
    return null
  }
}
