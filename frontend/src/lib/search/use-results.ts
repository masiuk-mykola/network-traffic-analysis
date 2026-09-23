'use client'

import { useInfiniteQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { searchResultsKey } from '@api/keys'

import { readResultsPage } from './results-page'
import { useResultTail, type Cursor } from './use-result-tail'
import { DEFAULT_SORT, type SortKey } from './sort'

export { PAGE_SIZE } from './results-page'

/**
 * Pages of matched sessions. A page ends with a cursor (more now), without one while the job runs
 * (caught up — `useResultTail` polls that last page alone), or without one once complete. Filled
 * pages never change, so nothing here goes stale.
 *
 * The order is in the key because a cursor belongs to the order it was issued in; it is sent only
 * to a finished job, since sorting a running one is refused.
 */
export function useResults(
  searchId: string | null,
  isRunning: boolean,
  sort: SortKey = DEFAULT_SORT,
) {
  const queryKey = useMemo(() => searchResultsKey(searchId ?? '', sort), [searchId, sort])

  const results = useInfiniteQuery({
    queryKey,
    initialPageParam: undefined as Cursor,
    queryFn: ({ pageParam, signal }) =>
      readResultsPage({ searchId: searchId ?? '', sort, isRunning, cursor: pageParam, signal }),
    getNextPageParam: (lastPage): Cursor => lastPage.next_cursor ?? undefined,
    enabled: Boolean(searchId),
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    // Old rows stay up while a new order of the same search loads; another search's never do.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === (searchId ?? '') ? previous : undefined,
  })
  // Those rows' cursors belong to the old order.
  const settled = !results.isPlaceholderData

  const tail = useResultTail({
    searchId,
    sort,
    isRunning,
    queryKey,
    pages: settled ? results.data : undefined,
    dataUpdatedAt: results.dataUpdatedAt,
  })

  // A retry re-arms whichever read stopped — the next page or the tail, never the settled pages.
  return {
    ...results,
    error: results.error ?? tail.error,
    isError: results.isError || tail.isError,
    hasNextPage: settled && results.hasNextPage,
    fetchNextPage: async () => {
      if (settled) await results.fetchNextPage()
    },
    retry: () => {
      if (!settled) return
      if (results.hasNextPage) void results.fetchNextPage()
      else void tail.refetch()
    },
  }
}
