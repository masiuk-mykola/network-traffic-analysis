import type { components } from '@api/schema'

export type Search = components['schemas']['Search']

/**
 * A job the server discarded. It is not a failure: ten minutes without anyone reading a search and
 * the API drops it and frees its slot, which is a thing to explain, not an error to apologise for.
 */
export const EXPIRED = { expired: true } as const

export type SearchStatus = Search | typeof EXPIRED

export type Ending = {
  kind: 'done' | 'failed' | 'cancelled' | 'expired'
  detail: string | null
}

export function isExpired(status: SearchStatus): status is typeof EXPIRED {
  return 'expired' in status
}

export function isRunning(status: SearchStatus): boolean {
  return !isExpired(status) && (status.state === 'queued' || status.state === 'running')
}

export function isFinished(status: SearchStatus): boolean {
  return !isRunning(status)
}

export function endingOf(status: SearchStatus): Ending | null {
  if (isExpired(status)) {
    return {
      kind: 'expired',
      detail: 'Nobody read this search for a while, so the server discarded it. Run it again.',
    }
  }

  switch (status.state) {
    case 'done':
      return { kind: 'done', detail: null }
    case 'cancelled':
      return { kind: 'cancelled', detail: null }
    case 'failed':
      return { kind: 'failed', detail: reasonFor(status) }
    default:
      return null
  }
}

export type Progress = {
  percent: number
  scanned: number
  total: number | null
  matched: number | null
  /** The server says when its own count is a projection rather than a tally. */
  matchedIsEstimate: boolean
}

export function progressOf(status: SearchStatus): Progress {
  if (isExpired(status)) {
    return { percent: 0, scanned: 0, total: null, matched: null, matchedIsEstimate: false }
  }

  const progress = status.progress
  return {
    percent: progress.percent ?? 0,
    scanned: progress.scanned_sessions ?? 0,
    total: progress.total_sessions_estimate ?? null,
    matched: progress.matched ?? null,
    matchedIsEstimate: progress.matched_is_estimate ?? false,
  }
}

function reasonFor(search: Search): string | null {
  const error = (search as { error?: { detail?: string } }).error
  return error?.detail ?? null
}
