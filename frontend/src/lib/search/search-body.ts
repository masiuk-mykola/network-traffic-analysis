import type { components } from '@api/schema'

import { toFilterNode, type FieldCatalogue } from './condition'
import { describeQuery, type QueryState } from './query-params'

export type SearchBody = components['schemas']['SearchCreate']

const NEWEST_FIRST = '-ts'

/** What `POST /v1/searches` takes, or null while the query is not runnable. */
export function toSearchBody(state: QueryState, fields: FieldCatalogue): SearchBody | null {
  if (describeQuery(state, fields) !== null) return null
  if (!state.from || !state.to) return null

  return {
    sensor_ids: state.sensorIds,
    from: state.from,
    to: state.to,
    // No conditions means every session in the window, which is what an empty `all` says.
    filter: toFilterNode(state.conditions, state.join, fields) ?? { all: [] },
    sort: NEWEST_FIRST,
  }
}

/**
 * A label derived from the search itself. The API replays a request carrying a label it has seen,
 * so pressing twice or retrying after a timeout returns the job already started instead of a twin —
 * while an edited query hashes differently and correctly starts a new one.
 */
export function idempotencyKeyFor(body: SearchBody): string {
  const serialized = JSON.stringify(body)
  return `s-${hash(serialized, 0x811c9dc5)}${hash(serialized, 0x01000193)}`
}

/** FNV-1a, twice with different seeds: deterministic, synchronous, and long enough here. */
function hash(value: string, seed: number): string {
  let result = seed
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index)
    result = Math.imul(result, 0x01000193)
  }
  return (result >>> 0).toString(36).padStart(7, '0')
}
