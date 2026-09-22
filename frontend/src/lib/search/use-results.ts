'use client'

import { useInfiniteQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { searchResultsKey } from '@api/keys'

import { readResultsPage } from './results-page'
import { useResultTail, type Cursor } from './use-result-tail'
import { DEFAULT_SORT, type SortKey } from './sort'

export { PAGE_SIZE } from './results-page'

/**
 * Pages of matched sessions. Rows arrive while the search still runs, so a page can end three ways:
 * with a cursor (there is more now), without one while the job runs (caught up — ask again later),
 * or without one once it is complete (that was everything).
 *
 * Only the first is a next page. The middle case would spin an infinite query, so it is left to
 * `useResultTail`, which reads the last page alone. Refetching the query itself would re-read every
 * page the table has loaded, in order, on every tick — and a page the job has already filled cannot
 * change, because matches are appended and a cursor is a position in them. That is also why nothing
 * here goes stale: the only page that moves is the tail, and the tail is kept fresh separately.
 *
 * The order is part of the key, never a parameter of the same query: a cursor belongs to the order
 * it was issued in, and the server rejects it in any other. It is also asked for only once the job
 * has finished — sorting a running search is refused, and a refused request is scored against us.
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
  })

  const tail = useResultTail({
    searchId,
    sort,
    isRunning,
    queryKey,
    pages: results.data,
    dataUpdatedAt: results.dataUpdatedAt,
  })

  // A refused tail read is the results read failing, and the screen reports it where the rows are.
  // Its retry re-arms whichever read stopped: the next page when there is a cursor to follow, the
  // tail when there is not — never the pages behind them, which cannot have changed.
  return {
    ...results,
    error: results.error ?? tail.error,
    isError: results.isError || tail.isError,
    retry: () => {
      if (results.hasNextPage) void results.fetchNextPage()
      else void tail.refetch()
    },
  }
}
