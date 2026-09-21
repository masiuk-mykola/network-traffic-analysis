'use client'

import Link from 'next/link'
import { useState } from 'react'

import { isHttpError } from '@api/http-error'
import {
  describeRelated,
  RELATED_WINDOWS,
  type RelatedRow,
  type RelatedWindow,
} from '@lib/session/related'
import { useRelated } from '@lib/session/use-related'
import { EmptyState, ErrorState, LoadingState } from '@/components/states'
import { Button } from '@/components/ui'

/**
 * What else the server relates to this session, within a window around it. The server does not say
 * why it relates them, so neither does this list: it shows the sessions and gets out of the way.
 */
export function RelatedSessions({ sessionId }: { sessionId: string }) {
  const [window, setWindow] = useState<RelatedWindow>('1h')
  const related = useRelated(sessionId, window)

  const rows = related.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <section aria-label="Related sessions" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted text-xs tracking-wide uppercase">Around this session</p>
        <div className="flex items-center gap-1">
          {RELATED_WINDOWS.map((option) => (
            <Button
              key={option.value}
              variant={window === option.value ? 'secondary' : 'ghost'}
              size="sm"
              aria-pressed={window === option.value}
              onClick={() => setWindow(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>
      </div>

      <Body
        related={related}
        rows={rows}
        onRetry={() => void related.refetch()}
        onMore={() => void related.fetchNextPage()}
      />
    </section>
  )
}

function Body({
  related,
  rows,
  onRetry,
  onMore,
}: {
  related: ReturnType<typeof useRelated>
  rows: RelatedRow[]
  onRetry: () => void
  onMore: () => void
}) {
  if (related.isPending) {
    return <LoadingState label="Looking around this session" className="min-h-24" />
  }

  if (related.isError) {
    // The session itself may be gone; that is a fact about this list, not a failure to retry.
    if (isHttpError(related.error) && related.error.status === 404) {
      return <p className="text-muted text-sm">The server has nothing around this session.</p>
    }
    return (
      <ErrorState
        error={related.error}
        onRetry={onRetry}
        retrying={related.isFetching}
        className="min-h-0 py-2"
      />
    )
  }

  if (rows.length === 0) {
    return (
      <EmptyState
        title="Nothing else in this window"
        description="No other session the server relates to this one. Try a wider window."
      />
    )
  }

  return (
    <div className="space-y-2">
      <ul className="border-border divide-border divide-y rounded-lg border">
        {rows.map((row) => {
          const line = describeRelated(row)
          return (
            <li key={row.id}>
              <Link
                href={line.href}
                className="hover:bg-accent/5 focus-visible:ring-ring/50 block px-3 py-2 focus-visible:ring-2 focus-visible:outline-none"
              >
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
                  <span className="text-muted text-xs">{line.when}</span>
                  <span className="font-medium">{line.protocol}</span>
                  <span className="break-all">
                    {line.from} → {line.to}
                  </span>
                  <span className="text-muted ml-auto text-xs">
                    {line.size} · risk {line.risk}
                  </span>
                </div>
              </Link>
            </li>
          )
        })}
      </ul>

      {related.hasNextPage ? (
        <Button
          variant="secondary"
          size="sm"
          disabled={related.isFetchingNextPage}
          onClick={onMore}
        >
          {related.isFetchingNextPage ? 'Reading on' : 'Read on'}
        </Button>
      ) : null}
    </div>
  )
}
