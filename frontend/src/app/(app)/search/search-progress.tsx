'use client'

import { CircleCheck, CircleSlash, Clock, TriangleAlert } from 'lucide-react'
import type { ReactElement } from 'react'

import { formatApproximate, formatCount } from '@lib/format'
import { endingOf, isRunning, progressOf, type SearchStatus } from '@lib/search/search-state'
import { useCancelSearch } from '@lib/search/use-cancel-search'
import { ErrorState } from '@/components/states'
import { Button } from '@/components/ui'

type SearchProgressProps = {
  searchId: string | null
  status: SearchStatus | undefined
  /** A poll that failed. The watching continues, so this is shown beside the numbers. */
  error: unknown
  isPending: boolean
}

export function SearchProgress({ searchId, status, error, isPending }: SearchProgressProps) {
  const cancel = useCancelSearch(searchId)

  if (!searchId) return null

  if (isPending && !status) {
    return (
      <p role="status" aria-live="polite" className="text-muted text-sm">
        Starting the search…
      </p>
    )
  }

  if (!status) return error ? <ErrorState error={error} className="min-h-0 py-2" /> : null

  const ending = endingOf(status)
  const progress = progressOf(status)
  const running = isRunning(status)

  return (
    <section aria-label="Search progress" className="border-border space-y-3 rounded-lg border p-3">
      <div className="flex items-center gap-3">
        {iconFor(ending?.kind)}
        <p className="text-sm font-medium">{headline(ending?.kind, running)}</p>

        {running ? (
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            disabled={cancel.isPending}
            onClick={() => cancel.mutate()}
          >
            {cancel.isPending ? 'Stopping' : 'Stop'}
          </Button>
        ) : null}
      </div>

      {running ? (
        <div className="space-y-1">
          <div
            role="progressbar"
            aria-valuenow={Math.round(progress.percent)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="bg-border h-1.5 w-full overflow-hidden rounded-full"
          >
            <div
              className="bg-accent h-full transition-[width] duration-300 ease-out"
              style={{ width: `${Math.min(100, Math.max(0, progress.percent))}%` }}
            />
          </div>
          <p className="text-muted text-xs">
            Scanned {formatCount(progress.scanned)}
            {progress.total === null ? '' : ` of about ${formatCount(progress.total)}`}
          </p>
        </div>
      ) : null}

      {progress.matched === null ? null : (
        <p className="text-sm">
          {progress.matchedIsEstimate ? (
            <>
              <span className="text-muted">≈</span> {formatApproximate(progress.matched)} matched so
              far <span className="text-muted text-xs">(estimated)</span>
            </>
          ) : (
            `${formatCount(progress.matched)} matched`
          )}
        </p>
      )}

      {ending?.detail ? <p className="text-muted text-sm">{ending.detail}</p> : null}

      {cancel.error ? <ErrorState error={cancel.error} className="min-h-0 py-2" /> : null}
      {error ? (
        <p role="alert" className="text-danger text-xs">
          Could not read the latest progress. Still watching.
        </p>
      ) : null}
    </section>
  )
}

function headline(kind: string | undefined, running: boolean): string {
  switch (kind) {
    case 'done':
      return 'Search finished'
    case 'failed':
      return 'Search failed'
    case 'cancelled':
      return 'Search cancelled'
    case 'expired':
      return 'Search discarded'
    default:
      return running ? 'Searching…' : 'Search'
  }
}

function iconFor(kind: string | undefined): ReactElement {
  const className = 'size-4 shrink-0'
  if (kind === 'done') return <CircleCheck aria-hidden className={`${className} text-accent`} />
  if (kind === 'failed') return <TriangleAlert aria-hidden className={`${className} text-danger`} />
  if (kind === 'cancelled' || kind === 'expired') {
    return <CircleSlash aria-hidden className={`${className} text-muted`} />
  }
  return <Clock aria-hidden className={`${className} text-muted animate-pulse`} />
}
