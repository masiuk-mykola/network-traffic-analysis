'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { enumKey } from '@api/keys'
import type { components } from '@api/schema'

type EnumResponse = components['schemas']['EnumResponse']

/**
 * The values a closed field allows. Fetched only once a field naming that catalogue is chosen, and
 * shared by every row that names it — asking twice for the same set is scored against us.
 */
export function useEnum(name: string | undefined) {
  return useQuery({
    queryKey: enumKey(name ?? ''),
    queryFn: ({ signal }) => fetchJson<EnumResponse>(`meta/enums/${name}`, { signal }),
    enabled: Boolean(name),
    staleTime: 30 * 60_000,
  })
}
