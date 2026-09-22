import { conditionsToParams } from './condition-params'
import type { FieldCatalogue } from './condition'
import { describeQuery, type QueryState } from './query-params'

/**
 * What `GET /v1/estimate` takes, or null while the query is not runnable. The completeness rules
 * are the form's own, so the estimate never asks about a query the form would refuse to run — the
 * server would only answer that with a 400 nobody can act on.
 */
export function toEstimateParams(
  state: QueryState,
  fields: FieldCatalogue,
): URLSearchParams | null {
  if (describeQuery(state, fields) !== null) return null
  if (!state.from || !state.to) return null
  if (describeEstimateGap(state) !== null) return null

  const params = new URLSearchParams()
  params.set('from', state.from)
  params.set('to', state.to)
  params.set('sensors', state.sensorIds.join(','))
  for (const condition of conditionsToParams(state.conditions)) params.append('f', condition)

  return params
}

/**
 * Why this query cannot be estimated, when the reason is worth saying.
 *
 * The endpoint takes repeated filters and ANDs them; it has no join. An any-joined pair would
 * therefore be estimated as the conjunction — "source is X and destination is X", which matches
 * nothing — and the screen would report a confident zero for a query the search answers with
 * hundreds. Better to ask nothing and say why.
 */
export function describeEstimateGap(state: QueryState): string | null {
  if (state.join !== 'any') return null
  if (conditionsToParams(state.conditions).length < 2) return null

  return 'No estimate for conditions joined with any — the estimate can only be asked about all of them at once. Run the search to see the size.'
}
