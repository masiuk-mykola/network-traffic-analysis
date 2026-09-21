import 'server-only'

import type { ZodType } from 'zod'

import { parseRetryAfter } from './retry-after'
import type { components } from './schema'

export { parseRetryAfter }

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

function baseUrl(): string {
  const url = process.env.CAPTURE_API_URL
  if (!url) throw new Error('CAPTURE_API_URL is not set')
  return url.replace(/\/+$/, '')
}

export type ApiRequest<T = unknown> = {
  method?: string
  path: string
  query?: URLSearchParams
  body?: unknown
  headers?: Record<string, string>
  token?: string
  timeoutMs?: number
  signal?: AbortSignal
  /** Validates the response body. Use the generated schemas from `./generated/zod.gen`. */
  schema?: ZodType<T>
}

export type ApiResponse<T> = {
  status: number
  data: T
  headers: Headers
}

/**
 * Raised when the API answers with a body the schema does not accept. It stays on the server:
 * the browser gets a generic 502, because the details describe our upstream, not the user's request.
 */
export class SchemaMismatchError extends Error {
  readonly path: string
  readonly issues: string[]

  constructor(path: string, issues: string[]) {
    super(`Unexpected response shape from ${path}`)
    this.name = 'SchemaMismatchError'
    this.path = path
    this.issues = issues
  }
}

/** One raw call: no retries and no refresh, so refresh stays single-flight in `session-store`. */
export async function rawFetch<T>(req: ApiRequest<T>): Promise<ApiResponse<T>> {
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
  return { status: res.status, data: validate(req, data, path), headers: res.headers }
}

function validate<T>(req: ApiRequest<T>, data: T, path: string): T {
  if (!req.schema || data === undefined) return data

  const parsed = req.schema.safeParse(data)
  if (!parsed.success) {
    throw new SchemaMismatchError(
      path,
      parsed.error.issues.map((issue) => `${issue.path.join('.') || '<root>'}: ${issue.message}`),
    )
  }
  return parsed.data
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
