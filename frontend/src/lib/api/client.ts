import 'server-only'

import type { components } from './schema'

export type ErrorBody = components['schemas']['ErrorBody']
export type TokenPair = components['schemas']['TokenPair']
export type Profile = components['schemas']['Profile']

const DEFAULT_TIMEOUT_MS = 15_000

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly retryAfterMs: number | null
  readonly body: ErrorBody | null

  constructor(status: number, body: ErrorBody | null, retryAfterMs: number | null) {
    super(body?.detail ?? `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = body?.code ?? 'http_error'
    this.retryAfterMs = retryAfterMs
    this.body = body
  }
}

/** The API sends `Retry-After` as seconds (429/503) or as an HTTP-date (login). */
export function parseRetryAfter(value: string | null, now = Date.now()): number | null {
  if (!value) return null
  const seconds = Number(value)
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000)
  const date = Date.parse(value)
  if (Number.isNaN(date)) return null
  return Math.max(0, date - now)
}

function baseUrl(): string {
  const url = process.env.CAPTURE_API_URL
  if (!url) throw new Error('CAPTURE_API_URL is not set')
  return url.replace(/\/+$/, '')
}

export type ApiRequest = {
  method?: string
  path: string
  query?: URLSearchParams
  body?: unknown
  headers?: Record<string, string>
  token?: string
  timeoutMs?: number
  signal?: AbortSignal
}

export type ApiResponse<T> = {
  status: number
  data: T
  headers: Headers
}

/** One raw call: no retries and no refresh, so refresh stays single-flight in `session-store`. */
export async function rawFetch<T>(req: ApiRequest): Promise<ApiResponse<T>> {
  const { method = 'GET', path, query, body, headers = {}, token, timeoutMs, signal } = req
  const url = `${baseUrl()}${path}${query && [...query].length > 0 ? `?${query}` : ''}`

  const timeout = AbortSignal.timeout(timeoutMs ?? DEFAULT_TIMEOUT_MS)
  const abort = signal ? AbortSignal.any([signal, timeout]) : timeout

  const init: RequestInit = {
    method,
    signal: abort,
    cache: 'no-store',
    headers: {
      accept: 'application/json',
      ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }

  const res = await fetch(url, init)

  if (!res.ok) {
    const problem = await readJson<ErrorBody>(res)
    throw new ApiError(res.status, problem, parseRetryAfter(res.headers.get('retry-after')))
  }

  const data = (res.status === 204 ? undefined : await readJson<T>(res)) as T
  return { status: res.status, data, headers: res.headers }
}

async function readJson<T>(res: Response): Promise<T | null> {
  const type = res.headers.get('content-type') ?? ''
  if (!type.includes('json')) return null
  try {
    return (await res.json()) as T
  } catch {
    return null
  }
}
