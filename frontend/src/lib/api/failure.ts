import { isHttpError } from './http-error'

/** What a failure looks like on screen. The only place that decides whether a retry is offered. */
export type Failure = {
  title: string
  detail: string
  /** The API's stable code, shown discreetly so it can be quoted in a report. */
  code: string | null
  retryable: boolean
  /** How long the server asked us to wait, when it said so. */
  retryAfterMs: number | null
  /** Identity of this particular failure; a later one gets a different value. */
  id: number | null
}

export function describeFailure(error: unknown): Failure {
  if (!isHttpError(error)) {
    return {
      title: 'Could not load this',
      detail: 'The request did not complete. Trying again may help.',
      code: null,
      retryable: true,
      retryAfterMs: null,
      id: null,
    }
  }

  const base = { code: error.code, retryAfterMs: error.retryAfterMs, id: error.id }

  if (error.code === 'session_revoked') {
    return {
      ...base,
      title: 'Your session ended',
      detail: 'Sign in again to continue.',
      retryable: false,
    }
  }

  if (error.status === 403) {
    return {
      ...base,
      title: 'You do not have access to this',
      detail: 'Your account cannot see this data. Ask for access, or sign in as someone who can.',
      retryable: false,
    }
  }

  if (error.status === 404 || error.status === 410) {
    return {
      ...base,
      title: 'Not found',
      detail: error.message,
      retryable: false,
    }
  }

  if (error.status === 429) {
    return {
      ...base,
      title: 'Too many requests',
      detail: 'The server asked us to slow down.',
      retryable: true,
    }
  }

  if (error.code === 'upstream_contract') {
    return {
      ...base,
      title: 'Something went wrong on our side',
      detail: 'The API answered in a way this app did not expect. Trying again may help.',
      retryable: true,
    }
  }

  if (error.status >= 500) {
    return {
      ...base,
      title: 'Could not load this',
      detail: 'The server is having trouble. Trying again may help.',
      retryable: true,
    }
  }

  // Anything else the API refused: its own wording is the most useful thing we have, and a
  // retry would only repeat the same rejected request.
  return {
    ...base,
    title: 'That request was refused',
    detail: error.message,
    retryable: false,
  }
}
