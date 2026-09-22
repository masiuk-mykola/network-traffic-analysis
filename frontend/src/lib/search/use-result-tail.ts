'use client'

import { useQuery, useQueryClient, type InfiniteData, type QueryKey } from '@tanstack/react-query'
import { useEffect } from 'react'

import { isHttpError } from '@api/http-error'

import { pollDelay, START_POLL_MS } from './poll-interval'
import { readResultsPage, tailChanged, type SearchResults } from './results-page'
import type { SortKey } from './sort'

/** A position in the job's matches. The head of the list is reached without one. */
export type Cursor = string | undefined

export type ResultPages = InfiniteData<SearchResults>

/** A page param is opaque to the table that carries it; anything but a cursor means the head. */
function asCursor(value: unknown): Cursor {
  return typeof value === 'string' ? value : undefined
}

/**
 * The page a running job is still adding to, kept fresh on its own.
 *
 * A search appends its matches, and a cursor is a position in that list, so every page the table
 * has already read is settled — only the last one can still grow. Refetching the infinite query
 * would read all of them again, page by page, on every tick; this reads the last one, at the cursor
 * it was issued for, and writes the answer back into the pages the table renders.
 *
 * The rows stay with the infinite query, so paging, sorting and the table above them are
 * unaffected; what comes back is only whether this read is failing, because a tail nobody can read
 * is the results read failing and the screen has to say so.
 */
export function useResultTail({
  searchId,
  sort,
  isRunning,
  queryKey,
  pages,
  dataUpdatedAt,
}: {
  searchId: string | null
  sort: SortKey
  isRunning: boolean
  /** The infinite query this tail belongs to. */
  queryKey: QueryKey
  pages: ResultPages | undefined
  dataUpdatedAt: number
}) {
  const client = useQueryClient()

  const held = pages?.pages.at(-1)
  const cursor = asCursor(pages?.pageParams.at(-1))
  // Caught up: no cursor to follow, and the job has not finished — so more may yet land here.
  const caughtUp = held !== undefined && held.next_cursor === null && !held.complete

  const tail = useQuery({
    queryKey: [...queryKey, 'tail', cursor ?? null],
    queryFn: ({ signal }) =>
      readResultsPage({ searchId: searchId ?? '', sort, isRunning, cursor, signal }),
    enabled: Boolean(searchId) && isRunning && caughtUp,
    // The page this stands for was just read by the query that owns it, so the tail starts from
    // that answer rather than asking for it again. The floor of the cadence is also how long that
    // answer counts as fresh: without it, becoming the tail would read the same address twice in
    // the same instant, which the API counts — and with it, a page read longer ago than that is
    // read again, which is not a repeat but the first tick of the poll.
    initialData: held,
    initialDataUpdatedAt: dataUpdatedAt,
    staleTime: START_POLL_MS,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchIntervalInBackground: false,
    refetchInterval: ({ state }) => {
      const error = state.error
      const advertised = isHttpError(error)
        ? { retryAfterMs: error.retryAfterMs, elapsedMs: Date.now() - state.errorUpdatedAt }
        : undefined
      return pollDelay(state.dataUpdateCount - 1, advertised)
    },
    // Held only while it is the tail; once the job moves past this cursor there is nothing to keep.
    gcTime: 0,
  })

  const fresh = tail.data
  useEffect(() => {
    if (!fresh) return

    client.setQueryData<ResultPages>(queryKey, (current) => {
      if (!current || current.pages.length === 0) return current

      const index = current.pages.length - 1
      // The table may have followed a cursor since this read began; that answer is not this page.
      if (asCursor(current.pageParams[index]) !== cursor) return current

      const last = current.pages[index]
      if (!last || !tailChanged(last, fresh)) return current

      return { ...current, pages: [...current.pages.slice(0, index), fresh] }
    })
  }, [client, cursor, fresh, queryKey])

  return { error: tail.error, isError: tail.isError, refetch: tail.refetch }
}
