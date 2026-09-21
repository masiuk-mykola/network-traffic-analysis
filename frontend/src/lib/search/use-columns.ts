'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { columnsKey } from '@api/keys'
import type { components } from '@api/schema'

export type ColumnDef = components['schemas']['ColumnDef']
type ColumnList = components['schemas']['ColumnList']

/** The columns this server publishes for a session table: order, widths, and what may be sorted. */
export function useColumns() {
  return useQuery({
    queryKey: columnsKey(),
    queryFn: ({ signal }) => fetchJson<ColumnList>('meta/columns', { signal }),
    staleTime: 30 * 60_000,
    select: (data) => data.items,
  })
}
