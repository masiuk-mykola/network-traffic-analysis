'use client'

import { Loader2, TriangleAlert } from 'lucide-react'

import { describeFailure } from '@api/failure'
import type { components } from '@api/schema'
import type { FieldCatalogue } from '@lib/search/condition'
import type { QueryState } from '@lib/search/query-params'
import { isGone } from '@lib/search/search-state'
import { toSearchBody } from '@lib/search/search-body'
import { useRunSearch } from '@lib/search/use-run-search'
import { useCountdown } from '@lib/use-countdown'
import { Button } from '@/components/ui'

import { SearchProgress } from './search-progress'

type Search = components['schemas']['Search']

type RunControlProps = {
  query: QueryState
  fields: FieldCatalogue
  /** Why the query cannot be run yet, if it cannot. */
  problem: string | null
  onStarted: (search: Search) => void
  /** The job this screen is watching, if any, with how the watching itself is going. */
  watching: {
    searchId: string | null
    status: Parameters<typeof SearchProgress>[0]['status']
    error: unknown
    isPending: boolean
  }
}

export function RunControl({ query, fields, problem, onStarted, watching }: RunControlProps) {
  const run = useRunSearch(onStarted)
  const failure = run.error ? describeFailure(run.error) : null

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <RunButton
          key={failure?.id ?? 'ready'}
          disabled={problem !== null}
          pending={run.isPending}
          waitMs={failure?.retryAfterMs ?? null}
          onRun={() => {
            const body = toSearchBody(query, fields)
            if (body) run.mutate(body)
          }}
        />
      </div>

      <SearchProgress {...watching} />

      {failure ? (
        <p role="alert" className="text-danger text-sm">
          {failure.title}. {failure.detail}
        </p>
      ) : null}

      {warningsOf(watching.status).length ? (
        <ul className="space-y-1">
          {warningsOf(watching.status).map((warning) => (
            <li
              key={`${warning.code}-${warning.sensor_id ?? ''}`}
              className="text-muted flex items-start gap-2 text-xs"
            >
              <TriangleAlert aria-hidden className="text-danger mt-0.5 size-3.5 shrink-0" />
              <span>
                {warning.detail}
                {warning.sensor_id ? ` (${warning.sensor_id})` : ''}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/** A job that is gone has no warnings to report; a running or finished one may. */
function warningsOf(status: RunControlProps['watching']['status']): Search['warnings'] {
  return status && !isGone(status) ? status.warnings : []
}

/**
 * Keyed by the failure so a refusal restarts the wait, and disabled while a request is in flight —
 * a second press would otherwise spend another of the three slots this account has.
 */
function RunButton({
  disabled,
  pending,
  waitMs,
  onRun,
}: {
  disabled: boolean
  pending: boolean
  waitMs: number | null
  onRun: () => void
}) {
  const waitSeconds = useCountdown(waitMs)

  return (
    <Button type="submit" disabled={disabled || pending || waitSeconds > 0} onClick={onRun}>
      {pending ? <Loader2 aria-hidden className="size-4 animate-spin" /> : null}
      {pending ? 'Starting' : waitSeconds > 0 ? `Try again in ${waitSeconds} s` : 'Run search'}
    </Button>
  )
}
