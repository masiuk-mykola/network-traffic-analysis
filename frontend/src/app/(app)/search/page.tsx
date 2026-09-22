import { ApiError } from '@api/client'
import { zGetSearchResponse, zListFieldsResponse } from '@api/generated/zod.gen'
import { holdRead } from '@api/hold'
import { callApi } from '@api/server'
import { requireProfile } from '@lib/auth/session'
import { ROUTES } from '@lib/routes'
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

  // The guard above resolved this already, so asking here costs nothing and spares the form a
  // round trip for the one thing it cannot work out on its own: which points this account may read.
  const profile = await requireProfile(ROUTES.search)
  const fields = await readFields()
  // A shared link can name a point this account cannot read. It is dropped here rather than
  // rendered as a choice that was made, so an unreadable point never becomes an active selection.
  const query = parseQuery(params, profile.sensor_ids, fields)
  const initialStatus = await readSearch(query.searchId)

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Search</h1>
        <p className="text-muted text-sm">
          Pick where to look and when. Conditions and results come next.
        </p>
      </div>

      <QueryForm
        initial={query}
        fields={fields}
        readable={profile.sensor_ids}
        initialStatus={initialStatus}
      />
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
    // Held with no window, so a running job's state is never reused: all this shares is the read
    // in flight, which is worth sharing in its own right. A refusal that named a delay is waited
    // out underneath, at the seam, because the API's window covers the whole template.
    const data = await holdRead(`searches/${searchId}`, 0, async () => {
      const answer = await callApi({
        path: `/v1/searches/${encodeURIComponent(searchId)}`,
        schema: zGetSearchResponse,
      })
      return answer.data
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
    // The hold keeps the server's own answer, under the same key the rationed route handler uses,
    // so whichever of the two asks first spares the other — including when the answer is a refusal.
    const data = await holdRead('meta/fields', 60_000, async () => {
      const answer = await callApi({ path: '/v1/meta/fields', schema: zListFieldsResponse })
      return answer.data
    })
    return Object.fromEntries(data.items.map((field) => [field.name, field]))
  } catch {
    // The form shows the failure and offers a retry; the page itself still renders.
    return {}
  }
}
