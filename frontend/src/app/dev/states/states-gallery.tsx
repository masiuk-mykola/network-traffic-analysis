'use client'

import { useEffect, useState } from 'react'

import { HttpError } from '@api/http-error'
import { EmptyState, ErrorState, LoadingState, Skeleton } from '@/components/states'
import { Button } from '@/components/ui'
import { useToast } from '@/components/toast/use-toast'

type Sample = { id: string; label: string; body: Record<string, unknown>; init: ResponseInit }

const SAMPLES: Sample[] = [
  {
    id: 'server',
    label: 'Server failure',
    body: { code: 'unavailable', detail: 'busy' },
    init: { status: 503 },
  },
  {
    id: 'permission',
    label: 'No permission',
    body: { code: 'forbidden', detail: 'observer' },
    init: { status: 403 },
  },
  {
    id: 'session',
    label: 'Session gone',
    body: { code: 'session_revoked', detail: 'sign in again' },
    init: { status: 401 },
  },
  {
    id: 'rate',
    label: 'Rate limited',
    body: { code: 'too_many_searches', detail: 'slow down' },
    init: { status: 429, headers: { 'retry-after': '5' } },
  },
]

export function StatesGallery() {
  const [errors, setErrors] = useState<Record<string, HttpError>>({})
  const [retries, setRetries] = useState(0)
  const { notify } = useToast()

  useEffect(() => {
    let cancelled = false
    void Promise.all(
      SAMPLES.map(async (sample) => [
        sample.id,
        await HttpError.fromResponse(Response.json(sample.body, sample.init)),
      ]),
    ).then((pairs) => {
      if (!cancelled) setErrors(Object.fromEntries(pairs) as Record<string, HttpError>)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="space-y-8">
      <section aria-label="Loading" className="border-border rounded border">
        <LoadingState label="Loading sessions" />
      </section>

      <section aria-label="Skeleton" className="border-border space-y-2 rounded border p-4">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-4 w-2/3" />
      </section>

      <section aria-label="Empty" className="border-border rounded border">
        <EmptyState
          title="No sessions match"
          description="Widen the time window or drop a condition."
          action={
            <Button variant="secondary" size="sm">
              Clear filters
            </Button>
          }
        />
      </section>

      {SAMPLES.map((sample) => {
        const error = errors[sample.id]
        return (
          <section
            key={sample.id}
            aria-label={sample.label}
            className="border-border rounded border"
          >
            {error ? <ErrorState error={error} onRetry={() => setRetries((n) => n + 1)} /> : null}
          </section>
        )
      })}

      <p data-testid="retry-count">retries: {retries}</p>

      <Button
        variant="secondary"
        size="sm"
        className="w-fit"
        onClick={() => notify({ title: 'Search cancelled', detail: 'The slot is free again.' })}
      >
        Show a toast
      </Button>
    </div>
  )
}
