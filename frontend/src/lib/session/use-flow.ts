'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { sessionFlowKey } from '@api/keys'
import type { components } from '@api/schema'

type SessionFlow = components['schemas']['SessionFlow']

/**
 * A closed session's traffic is history: each width is read once and kept, so going back to a width
 * already looked at costs nothing. The width is part of the key; the metric is not, because it
 * changes nothing about what was asked for.
 */
export function useFlow(sessionId: string, bucketMs: number | null) {
  return useQuery({
    queryKey: sessionFlowKey(sessionId, bucketMs ?? undefined),
    queryFn: ({ signal }) => {
      const query = new URLSearchParams({ bucket_ms: String(bucketMs) })
      return fetchJson<SessionFlow>(`sessions/${encodeURIComponent(sessionId)}/flow`, {
        query,
        signal,
      })
    },
    enabled: Boolean(sessionId) && bucketMs !== null,
    staleTime: Infinity,
  })
}
