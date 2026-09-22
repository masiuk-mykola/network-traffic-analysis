import { ApiError } from '@api/client'
import { zGetSearchResponse, zListFieldsResponse } from '@api/generated/zod.gen'
import { holdRead } from '@api/hold'
import { callApi } from '@api/server'
import type { FieldCatalogue } from '@lib/search/condition'
import { parseQuery } from '@lib/search/query-params'
import { EXPIRED, MISSING, type Search, type SearchStatus } from '@lib/search/search-state'

import { QueryForm } from './query-form'

export default async function SearchPage({ searchParams }: PageProps<'/search'>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(await searchParams)) {
    for (const item of Array.isArray(value) ? value : [value ?? '']) {
      if (item) params.append(key, item)
    }
  }

  const fields = await readFields()
  const query = parseQuery(params, undefined, fields)
  const initialStatus = await readSearch(query.searchId)

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Search</h1>
        <p className="text-muted text-sm">
          Pick where to look and when. Conditions and results come next.
        </p>
      </div>

      <QueryForm initial={query} fields={fields} initialStatus={initialStatus} />
    </main>
  )
}

/**
 * A shared address names a job that may be finished, discarded, or nobody's. Reading it here means
 * the browser inherits the answer instead of asking for it — and a job that is not there is denied
 * once, on the server, rather than by every copy of the screen React mounts.
 */
async function readSearch(searchId: string | null): Promise<SearchStatus | undefined> {
  if (!searchId) return undefined

  try {
    const { data } = await callApi({
      path: `/v1/searches/${encodeURIComponent(searchId)}`,
      schema: zGetSearchResponse,
    })
    return data as Search
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return MISSING
    if (error instanceof ApiError && error.status === 410) return EXPIRED
    // Anything else is the client's problem to report, with its retry.
    return undefined
  }
}

/**
 * Read on the server so a shared link's conditions can be understood before anything renders; the
 * form hands the same catalogue to its query, so the browser does not ask for it again.
 */
async function readFields(): Promise<FieldCatalogue> {
  try {
    // Held for a minute: the catalogue changes with a deploy, and a render that happens twice would
    // otherwise ask twice — which the API counts, and which turns a refusal with a delay attached
    // into a violation of a delay this page never saw.
    return await holdRead('meta/fields', 60_000, async () => {
      const { data } = await callApi({ path: '/v1/meta/fields', schema: zListFieldsResponse })
      return Object.fromEntries(data.items.map((field) => [field.name, field]))
    })
  } catch {
    // The form shows the failure and offers a retry; the page itself still renders.
    return {}
  }
}
