/** The API refuses a search that names more capture points than this. */
export const MAX_SENSORS = 5

export type QueryState = {
  sensorIds: string[]
  from: string | null
  to: string | null
}

export const EMPTY_QUERY: QueryState = { sensorIds: [], from: null, to: null }

/**
 * The query lives in the address bar, which means it arrives from strangers: a shared link can name
 * points this account cannot read, repeat them, carry more than the API accepts, or hold a window
 * that runs backwards. Nothing here throws — anything unusable is simply dropped.
 */
export function parseQuery(params: URLSearchParams, readable?: readonly string[]): QueryState {
  const named = params.getAll('sensor').flatMap((value) => value.split(','))
  const allowed = readable ? new Set(readable) : null

  const sensorIds = [...new Set(named.map((id) => id.trim()).filter(Boolean))]
    .filter((id) => !allowed || allowed.has(id))
    .slice(0, MAX_SENSORS)

  return { sensorIds, ...parseWindow(params.get('from'), params.get('to')) }
}

export function toQueryString(state: QueryState): string {
  const params = new URLSearchParams()
  for (const id of state.sensorIds) params.append('sensor', id)
  if (state.from && state.to) {
    params.set('from', state.from)
    params.set('to', state.to)
  }
  return params.toString()
}

function parseWindow(from: string | null, to: string | null): Pick<QueryState, 'from' | 'to'> {
  if (!from || !to) return { from: null, to: null }

  const start = Date.parse(from)
  const end = Date.parse(to)
  if (Number.isNaN(start) || Number.isNaN(end) || start >= end) return { from: null, to: null }

  return { from, to }
}
