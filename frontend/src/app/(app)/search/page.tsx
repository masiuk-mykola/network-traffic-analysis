import { parseQuery } from '@lib/search/query-params'

import { QueryForm } from './query-form'

export default async function SearchPage({ searchParams }: PageProps<'/search'>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(await searchParams)) {
    for (const item of Array.isArray(value) ? value : [value ?? '']) {
      if (item) params.append(key, item)
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Search</h1>
        <p className="text-muted text-sm">
          Pick where to look and when. Conditions and results come next.
        </p>
      </div>

      <QueryForm initial={parseQuery(params)} />
    </main>
  )
}
