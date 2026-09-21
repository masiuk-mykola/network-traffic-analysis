'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { isHttpError } from '@api/http-error'
import { searchKey } from '@api/keys'

import { nextPollDelay } from './poll-interval'
import { EXPIRED, isRunning, MISSING, type Search, type SearchStatus } from './search-state'

/** What the page already knows about the job its address names, and which job that was. */
export type InitialStatus = { searchId: string | null; status: SearchStatus | undefined }

/**
 * The job named in the address bar, watched while it runs.
 *
 * The interval comes from the job's own state rather than from a timer this hook owns: once the
 * state is an ending there is no interval at all, so polling cannot outlive the search. Reading is
 * also what keeps a job alive — the server discards one nobody has read for ten minutes — but a
 * hidden tab stops asking, and that case is reported as its own ending rather than as a failure.
 */
export function useSearch(searchId: string | null, initial?: InitialStatus) {
  const inherited = initial && initial.searchId === searchId ? initial.status : undefined

  return useQuery<SearchStatus>({
    queryKey: searchKey(searchId ?? ''),
    queryFn: async ({ signal }) => {
      try {
        return await fetchJson<Search>(`searches/${encodeURIComponent(searchId ?? '')}`, { signal })
      } catch (error) {
        if (isHttpError(error) && error.status === 410) return EXPIRED
        // A shared address can name a job that was deleted, never existed, or belongs elsewhere.
        if (isHttpError(error) && error.status === 404) return MISSING
        throw error
      }
    },
    enabled: Boolean(searchId),
    // Read on the server for this address; asking again on mount would be the same answer twice.
    initialData: inherited,
    refetchInterval: ({ state }) => {
      const status = state.data
      if (!status || !isRunning(status)) return false
      // One successful read has already happened by now, so the first wait is the shortest.
      return nextPollDelay(state.dataUpdateCount - 1)
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  })
}
