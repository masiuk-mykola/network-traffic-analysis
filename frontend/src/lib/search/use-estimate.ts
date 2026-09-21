'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { estimateKey } from '@api/keys'
import type { components } from '@api/schema'

type EstimateResponse = components['schemas']['EstimateResponse']

/**
 * How large this query would be. The capture is a fixed window in the past, so the answer cannot
 * drift: it is fetched once per distinct query and never refetched on its own. The endpoint allows
 * only a few requests per second, and the caller hands it a settled query rather than a live one.
 */
export function useEstimate(params: URLSearchParams | null) {
  const search = params?.toString() ?? ''

  return useQuery({
    queryKey: estimateKey(search),
    queryFn: ({ signal }) =>
      fetchJson<EstimateResponse>('estimate', { query: params ?? undefined, signal }),
    enabled: params !== null,
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  })
}
