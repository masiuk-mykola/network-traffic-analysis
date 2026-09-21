'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { protocolSchemaKey } from '@api/keys'
import type { components } from '@api/schema'

type ProtocolSchema = components['schemas']['ProtocolSchema']

/** How this protocol's transaction is described: labels, order, and the kind of each value. */
export function useProtocolSchema(protocol: string | null) {
  return useQuery({
    queryKey: protocolSchemaKey(protocol ?? ''),
    queryFn: ({ signal }) =>
      fetchJson<ProtocolSchema>(`meta/schema/${encodeURIComponent(protocol ?? '')}`, { signal }),
    enabled: Boolean(protocol),
    // It changes with a deploy, not with a visit.
    staleTime: 30 * 60_000,
    select: (data) => data.fields,
  })
}
