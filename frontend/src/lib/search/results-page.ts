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

/**
 * One page of matched sessions, asked for identically wherever it is asked from — the head, a
 * cursor the table followed, or the tail a running job is still adding to. One reader, so those
 * three can never disagree about the limit, the order, or what happens to a cursor.
 */
export function readResultsPage({
  searchId,
  sort,
  isRunning,
  cursor,
  signal,
}: ResultsRequest): Promise<SearchResults> {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) })
  if (!isRunning && sort !== DEFAULT_SORT) query.set('sort', sort)
  // The cursor is opaque and bound to this search: it goes back exactly as it arrived.
  if (cursor) query.set('cursor', cursor)

  return fetchJson<SearchResults>(`searches/${encodeURIComponent(searchId)}/results`, {
    query,
    signal,
  })
}

/**
 * Whether a freshly read tail says anything the held one did not.
 *
 * The server appends matches to the end of the job's list and a cursor is a position in it, so a
 * page read at the same cursor can only have grown: the rows it already held cannot change. Equal
 * length therefore means equal rows, and there is nothing to write back.
 */
export function tailChanged(held: SearchResults, fresh: SearchResults): boolean {
  return (
    held.items.length !== fresh.items.length ||
    held.next_cursor !== fresh.next_cursor ||
    held.complete !== fresh.complete
  )
}
