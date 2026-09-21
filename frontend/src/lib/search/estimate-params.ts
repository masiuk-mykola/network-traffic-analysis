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

  const params = new URLSearchParams()
  params.set('from', state.from)
  params.set('to', state.to)
  params.set('sensors', state.sensorIds.join(','))
  for (const condition of conditionsToParams(state.conditions)) params.append('f', condition)

  return params
}
