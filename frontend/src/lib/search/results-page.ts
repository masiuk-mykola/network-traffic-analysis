import { fetchJson } from '@api/fetch-json'
import type { components } from '@api/schema'

import { DEFAULT_SORT, type SortKey } from './sort'

export type SearchResults = components['schemas']['SearchResults']

/** The server clamps anything larger and reports what it applied; asking for more is scored. */
export const PAGE_SIZE = 500

export type ResultsRequest = {
  searchId: string
  sort: SortKey
  /** A running job is read in its own scan order; asking for another is refused. */
  isRunning: boolean
  cursor?: string
  signal?: AbortSignal
}

/** The one reader for the head, a followed cursor and the tail, so they cannot disagree. */
export function readResultsPage({
  searchId,
  sort,
  isRunning,
  cursor,
  signal,
}: ResultsRequest): Promise<SearchResults> {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) })
  if (!isRunning && sort !== DEFAULT_SORT) query.set('sort', sort)
  // Opaque: sent back exactly as it arrived.
  if (cursor) query.set('cursor', cursor)

  return fetchJson<SearchResults>(`searches/${encodeURIComponent(searchId)}/results`, {
    query,
    signal,
  })
}

/**
 * Matches are only appended, so a page read again at the same cursor can only have grown: equal
 * length means equal rows.
 */
export function tailChanged(held: SearchResults, fresh: SearchResults): boolean {
  return (
    held.items.length !== fresh.items.length ||
    held.next_cursor !== fresh.next_cursor ||
    held.complete !== fresh.complete
  )
}
