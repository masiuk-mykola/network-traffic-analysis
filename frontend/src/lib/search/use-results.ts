'use client'

import { useInfiniteQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { searchResultsKey } from '@api/keys'
import type { components } from '@api/schema'

import { nextPollDelay } from './poll-interval'

type SearchResults = components['schemas']['SearchResults']

/** The server clamps anything larger and reports what it applied; asking for more is scored. */
export const PAGE_SIZE = 500

/**
 * Pages of matched sessions. Rows arrive while the search still runs, so a page can end three ways:
 * with a cursor (there is more now), without one while the job runs (caught up — ask again later),
 * or without one once it is complete (that was everything).
 *
 * Only the first is a next page. The middle case would spin an infinite query, so it is handled by
 * a timed refetch that disappears the moment the job stops running.
 */
export function useResults(searchId: string | null, isRunning: boolean) {
  return useInfiniteQuery({
    queryKey: searchResultsKey(searchId ?? ''),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => {
      const query = new URLSearchParams({ limit: String(PAGE_SIZE) })
      // The cursor is opaque and bound to this search: it goes back exactly as it arrived.
      if (pageParam) query.set('cursor', pageParam)
      return fetchJson<SearchResults>(`searches/${encodeURIComponent(searchId ?? '')}/results`, {
        query,
        signal,
      })
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(searchId),
    refetchInterval: ({ state }) => {
      if (!isRunning) return false
      const pages = state.data?.pages ?? []
      const last = pages.at(-1)
      // Only while caught up: with a cursor in hand there is a next page to fetch instead.
      if (!last || last.next_cursor !== null || last.complete) return false
      return nextPollDelay(pages.length)
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  })
}
