import type { components } from '@api/schema'

export type SortKey = NonNullable<components['schemas']['SearchCreate']['sort']>
export type SortDirection = 'ascending' | 'descending'

/** The order a search is created with, and the only one the server serves while it runs. */
export const DEFAULT_SORT: SortKey = '-ts'

const SORT_KEYS: readonly SortKey[] = ['ts', '-ts', 'bytes', '-bytes', 'risk', '-risk']

/** Published column key -> the field the server sorts on. A column missing here cannot be sorted. */
const FIELDS: Record<string, string> = {
  start: 'ts',
  bytes: 'bytes',
  risk: 'risk',
}

/** Orders arrive from the address bar, so anything outside the vocabulary is simply not an order. */
export function parseSortKey(value: string | null): SortKey | null {
  return SORT_KEYS.find((key) => key === value) ?? null
}

export function sortFieldFor(columnKey: string): string | null {
  return FIELDS[columnKey] ?? null
}

export function directionOf(sort: SortKey, columnKey: string): SortDirection | null {
  const field = sortFieldFor(columnKey)
  if (!field) return null
  if (sort === field) return 'ascending'
  if (sort === `-${field}`) return 'descending'
  return null
}

/**
 * One click on a header: a column that is not in force starts at its most interesting end (newest,
 * biggest, riskiest first), the one in force flips, and flipping it off returns to the default.
 */
export function toggleSort(sort: SortKey, columnKey: string): SortKey {
  const field = sortFieldFor(columnKey)
  if (!field) return sort

  const direction = directionOf(sort, columnKey)
  if (direction === null) return `-${field}` as SortKey
  if (direction === 'descending') return field as SortKey
  return DEFAULT_SORT
}
