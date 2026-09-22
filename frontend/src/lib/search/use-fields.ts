'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { fieldsKey } from '@api/keys'
import type { components } from '@api/schema'

import type { FieldCatalogue } from './condition'

type FieldList = components['schemas']['FieldList']

/** The searchable fields this server publishes. Changes about as often as the server is deployed. */
export function useFields(initial?: FieldCatalogue) {
  const seeded = initial && Object.keys(initial).length > 0 ? initial : undefined

  return useQuery({
    queryKey: fieldsKey(),
    // Rationed by its own handler rather than passed through the proxy: this read and the search
    // page's server-side one share a hold, so neither repeats the other's ask or its refusal.
    queryFn: ({ signal }) => fetchJson<FieldList>('fields', { signal }),
    staleTime: 30 * 60_000,
    initialData: seeded ? { items: Object.values(seeded) } : undefined,
    select: (data): FieldCatalogue =>
      Object.fromEntries(data.items.map((field) => [field.name, field])),
  })
}
