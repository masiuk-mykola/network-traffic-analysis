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
 * cannot end up as two entries. Ids are opaque strings and are never re-encoded.
 */

export type QueryKey = readonly unknown[]

export const sensorsKey = () => ['sensors'] as const

export const fieldsKey = () => ['fields'] as const

export const healthKey = () => ['health'] as const

export const columnsKey = () => ['columns'] as const

export const enumKey = (name: string) => ['enum', name] as const

/** Keyed by the exact query string the endpoint is asked with, so two different queries never share. */
export const estimateKey = (search: string) => ['estimate', search] as const

export const searchKey = (searchId: string) => ['search', searchId] as const

/** The order is part of the identity: a cursor belongs to one order and the server refuses it in another. */
export const searchResultsKey = (searchId: string, sort?: string) =>
  ['search', searchId, 'results', sort ?? null] as const

export const sessionKey = (sessionId: string) => ['session', sessionId] as const

export const sessionFlowKey = (sessionId: string, bucketMs?: number) =>
  ['session', sessionId, 'flow', bucketMs ?? null] as const

/** The window is part of the identity: a cursor issued for one window is invalid in another. */
export const sessionRelatedKey = (sessionId: string, window?: string) =>
  ['session', sessionId, 'related', window ?? null] as const

export const protocolSchemaKey = (protocol: string) => ['protocol-schema', protocol] as const

/**
 * The newest page of detections, which seeds the live feed. The feed itself is pushed rather than
 * queried, so this key names the seed only — it is never re-read on a tick.
 */
export const detectionsKey = () => ['detections'] as const
