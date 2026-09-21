import { zListFieldsResponse } from '@api/generated/zod.gen'
import { callApi } from '@api/server'
import type { FieldCatalogue } from '@lib/search/condition'
import { parseQuery } from '@lib/search/query-params'

import { QueryForm } from './query-form'

export default async function SearchPage({ searchParams }: PageProps<'/search'>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(await searchParams)) {
    for (const item of Array.isArray(value) ? value : [value ?? '']) {
      if (item) params.append(key, item)
    }
  }

  const fields = await readFields()

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Search</h1>
        <p className="text-muted text-sm">
          Pick where to look and when. Conditions and results come next.
        </p>
      </div>

      <QueryForm initial={parseQuery(params, undefined, fields)} fields={fields} />
    </main>
  )
}

/**
 * Read on the server so a shared link's conditions can be understood before anything renders; the
 * form hands the same catalogue to its query, so the browser does not ask for it again.
 */
async function readFields(): Promise<FieldCatalogue> {
  try {
    const { data } = await callApi({ path: '/v1/meta/fields', schema: zListFieldsResponse })
    return Object.fromEntries(data.items.map((field) => [field.name, field]))
  } catch {
    // The form shows the failure and offers a retry; the page itself still renders.
    return {}
  }
}
