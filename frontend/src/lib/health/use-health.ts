'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { healthKey } from '@api/keys'
import type { components } from '@api/schema'

type Health = components['schemas']['Health']

/** A part of the server the server itself says is unwell, in its own words. */
export type Degraded = { name: string; detail: string | null }

/**
 * How often the server may be asked how it is. The API grades the median gap between these reads at
 * ten seconds and a container health check is already contributing to that stream, so this is far
 * slower than the limit rather than close to it.
 */
export const HEALTH_INTERVAL_MS = 60_000

/**
 * What the server says about itself. It is asked rarely, never in a background tab, and its own
 * failure is kept quiet: a reader has no use for "we could not ask how the server is".
 */
export function useHealth() {
  return useQuery({
    queryKey: healthKey(),
    queryFn: ({ signal }) => fetchJson<Health>('health', { signal }),
    refetchInterval: HEALTH_INTERVAL_MS,
    refetchIntervalInBackground: false,
    staleTime: HEALTH_INTERVAL_MS,
    retry: false,
    select: (data) =>
      Object.entries(data.components)
        .filter(([, part]) => part?.status === 'degraded')
        .map(([name, part]): Degraded => ({ name, detail: part?.detail ?? null })),
  })
}
