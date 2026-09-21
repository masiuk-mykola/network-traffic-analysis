'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { isHttpError } from '@api/http-error'
import { searchKey } from '@api/keys'

import { nextPollDelay } from './poll-interval'
import { EXPIRED, isRunning, type Search, type SearchStatus } from './search-state'

/**
 * The job named in the address bar, watched while it runs.
 *
 * The interval comes from the job's own state rather than from a timer this hook owns: once the
 * state is an ending there is no interval at all, so polling cannot outlive the search. Reading is
 * also what keeps a job alive — the server discards one nobody has read for ten minutes — but a
 * hidden tab stops asking, and that case is reported as its own ending rather than as a failure.
 */
export function useSearch(searchId: string | null) {
  return useQuery<SearchStatus>({
    queryKey: searchKey(searchId ?? ''),
    queryFn: async ({ signal }) => {
      try {
        return await fetchJson<Search>(`searches/${encodeURIComponent(searchId ?? '')}`, { signal })
      } catch (error) {
        if (isHttpError(error) && error.status === 410) return EXPIRED
        throw error
      }
    },
    enabled: Boolean(searchId),
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
