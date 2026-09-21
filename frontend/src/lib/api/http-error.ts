import { parseRetryAfter } from './retry-after'

let nextId = 0

/** What a failed call looks like to the browser. Built from our own proxy's response. */
export class HttpError extends Error {
  /** Distinguishes one failure from the next, even when they say the same thing. */
  readonly id: number
  readonly status: number
  readonly code: string
  /** The whole error envelope, including any machine-readable extras. Null when it was not JSON. */
  readonly body: Record<string, unknown> | null
  readonly retryAfterMs: number | null

  private constructor(
    status: number,
    code: string,
    detail: string,
    body: Record<string, unknown> | null,
    retryAfterMs: number | null,
  ) {
    super(detail)
    this.name = 'HttpError'
    nextId += 1
    this.id = nextId
    this.status = status
    this.code = code
    this.body = body
    this.retryAfterMs = retryAfterMs
  }

  static async fromResponse(res: Response): Promise<HttpError> {
    const body = await readEnvelope(res)
    const code = typeof body?.code === 'string' ? body.code : 'http_error'
    const detail =
      typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status} ${res.statusText}`.trim()

    return new HttpError(
      res.status,
      code,
      detail,
      body,
      parseRetryAfter(res.headers.get('retry-after')),
    )
  }
}

export function isHttpError(error: unknown): error is HttpError {
  return error instanceof HttpError
}

async function readEnvelope(res: Response): Promise<Record<string, unknown> | null> {
  if (!(res.headers.get('content-type') ?? '').includes('json')) return null
  try {
    const parsed: unknown = await res.json()
    return typeof parsed === 'object' && parsed !== null
      ? (parsed as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}
