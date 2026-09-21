import { conditionsToParams, parseConditions } from './condition-params'
import { describeCondition, type ConditionRow, type FieldCatalogue, type Join } from './condition'
import { DEFAULT_SORT, parseSortKey, type SortKey } from './sort'

/** The API refuses a search that names more capture points than this. */
export const MAX_SENSORS = 5

export type QueryState = {
  sensorIds: string[]
  from: string | null
  to: string | null
  conditions: ConditionRow[]
  join: Join
  /** The job this screen started, so a reload returns to it rather than to an empty form. */
  searchId: string | null
  /** The order the results are read in. The server sorts, and only once the job has finished. */
  sort: SortKey
}

export const EMPTY_QUERY: QueryState = {
  sensorIds: [],
  from: null,
  to: null,
  conditions: [],
  join: 'all',
  searchId: null,
  sort: DEFAULT_SORT,
}

/**
 * The query lives in the address bar, which means it arrives from strangers: a shared link can name
 * points this account cannot read, repeat them, carry more than the API accepts, or hold a window
 * that runs backwards. Nothing here throws — anything unusable is simply dropped.
 */
export function parseQuery(
  params: URLSearchParams,
  readable?: readonly string[],
  fields: FieldCatalogue = {},
): QueryState {
  const named = params.getAll('sensor').flatMap((value) => value.split(','))
  const allowed = readable ? new Set(readable) : null

  const sensorIds = [...new Set(named.map((id) => id.trim()).filter(Boolean))]
    .filter((id) => !allowed || allowed.has(id))
    .slice(0, MAX_SENSORS)

  return {
    sensorIds,
    ...parseWindow(params.get('from'), params.get('to')),
    conditions: parseConditions(params, fields),
    join: params.get('join') === 'any' ? 'any' : 'all',
    searchId: parseSearchId(params.get('search')),
    sort: parseSortKey(params.get('sort')) ?? DEFAULT_SORT,
  }
}

export function toQueryString(state: QueryState): string {
  const params = new URLSearchParams()
  for (const id of state.sensorIds) params.append('sensor', id)
  if (state.from && state.to) {
    params.set('from', state.from)
    params.set('to', state.to)
  }
  for (const condition of conditionsToParams(state.conditions)) params.append('f', condition)
  if (state.join === 'any' && state.conditions.length > 1) params.set('join', 'any')
  if (state.searchId) params.set('search', state.searchId)
  if (state.sort !== DEFAULT_SORT) params.set('sort', state.sort)
  return params.toString()
}

/** Ids are opaque to us; anything that is not a plausible one is simply not a search. */
function parseSearchId(value: string | null): string | null {
  return value && /^[A-Za-z0-9_-]{1,64}$/.test(value) ? value : null
}

function parseWindow(from: string | null, to: string | null): Pick<QueryState, 'from' | 'to'> {
  if (!from || !to) return { from: null, to: null }

  const start = Date.parse(from)
  const end = Date.parse(to)
  if (Number.isNaN(start) || Number.isNaN(end) || start >= end) return { from: null, to: null }

  return { from, to }
}

/**
 * What still stops this query from being run, in the words the person needs. Null when it is ready.
 * The form blocks its control on this and the estimate refuses to ask for anything else, so the two
 * can never disagree about whether a query is complete.
 */
export function describeQuery(state: QueryState, fields: FieldCatalogue): string | null {
  if (state.sensorIds.length === 0) return 'Choose at least one capture point.'
  if (state.sensorIds.length > MAX_SENSORS) return `Choose no more than ${MAX_SENSORS}.`
  if (!state.from || !state.to) return 'Choose a time window.'
  if (Date.parse(state.from) >= Date.parse(state.to)) return 'The window ends before it starts.'

  for (const row of state.conditions) {
    const unfinished = describeCondition(row, fields[row.field])
    if (unfinished) return `A condition is unfinished: ${unfinished.toLowerCase()}`
  }

  return null
}
