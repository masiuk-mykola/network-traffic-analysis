'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { searchKey } from '@api/keys'
import type { components } from '@api/schema'

type Search = components['schemas']['Search']

/** The job named in the address bar, so a reload shows what is already running. */
export function useSearch(searchId: string | null) {
  return useQuery({
    queryKey: searchKey(searchId ?? ''),
    queryFn: ({ signal }) =>
      fetchJson<Search>(`searches/${encodeURIComponent(searchId ?? '')}`, { signal }),
    enabled: Boolean(searchId),
  })
}
