/**
 * Every cache identity in the app is built here. Two callers asking for the same resource must
 * produce the same key, or the cache holds it twice and the request goes out twice — which the
 * backend scores as `http.get_dedupe`.
 *
 * Nested keys start with their parent's key on purpose: invalidating a search also drops every
 * page of its results. Do not invalidate a parent on a poll tick unless you mean to refetch the
 * whole subtree.
 *
 * Optional arguments are normalized to `null` rather than omitted, so `(id)` and `(id, undefined)`
 * cannot end up as two entries. Ids and cursors are opaque strings and are never re-encoded.
 */

export type QueryKey = readonly unknown[]

export type EstimateParams = {
  from: string
  to: string
  sensors?: readonly string[]
  filter?: unknown
}

export const sensorsKey = () => ['sensors'] as const

export const fieldsKey = () => ['fields'] as const

export const columnsKey = () => ['columns'] as const

export const enumKey = (name: string) => ['enum', name] as const

export const estimateKey = (params: EstimateParams) =>
  ['estimate', params.from, params.to, params.sensors ?? null, params.filter ?? null] as const

export const searchKey = (searchId: string) => ['search', searchId] as const

export const searchResultsKey = (searchId: string, cursor?: string) =>
  ['search', searchId, 'results', cursor ?? null] as const

export const sessionKey = (sessionId: string) => ['session', sessionId] as const

export const sessionFlowKey = (sessionId: string, bucketMs?: number) =>
  ['session', sessionId, 'flow', bucketMs ?? null] as const

export const protocolSchemaKey = (protocol: string) => ['protocol-schema', protocol] as const
