'use client'

import { useInfiniteQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { sessionRelatedKey } from '@api/keys'
import type { components } from '@api/schema'

import type { RelatedWindow } from './related'

type RelatedSessions = components['schemas']['RelatedSessions']

/**
 * The sessions the server relates to this one, a page at a time.
 *
 * The window is part of the key rather than a parameter of one query: a cursor belongs to the window
 * it was issued for, and the server rejects it in any other. What is around a closed session does
 * not change, so each window is read once and kept.
 */
export function useRelated(sessionId: string, window: RelatedWindow) {
  return useInfiniteQuery({
    queryKey: sessionRelatedKey(sessionId, window),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => {
      const query = new URLSearchParams({ window })
      // The cursor is opaque and belongs to this window: it goes back exactly as it arrived.
      if (pageParam) query.set('cursor', pageParam)
      return fetchJson<RelatedSessions>(`sessions/${encodeURIComponent(sessionId)}/related`, {
        query,
        signal,
      })
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(sessionId),
    staleTime: Infinity,
  })
}
