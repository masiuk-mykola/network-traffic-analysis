'use client'

import { tableFeatures, useTable, type ColumnDef as TableColumnDef } from '@tanstack/react-table'
import Link from 'next/link'
import { useMemo, useState } from 'react'

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

const features = tableFeatures({})

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
  // One line per session, and the line is the same four things every time. The link sits in the
  // first cell rather than around the row: a table row cannot be a link, and wrapping every cell in
  // one would announce the same destination four times.
  const columns = useMemo<TableColumnDef<typeof features, RelatedRow>[]>(
    () => [
      {
        id: 'when',
        header: 'Started',
        cell: ({ row }) => {
          const line = describeRelated(row.original)
          return (
            <Link
              href={line.href}
              className="focus-visible:ring-ring/50 text-muted block text-xs focus-visible:ring-2 focus-visible:outline-none"
            >
              {line.when}
            </Link>
          )
        },
      },
      {
        id: 'protocol',
        header: 'Protocol',
        cell: ({ row }) => (
          <span className="font-medium">{describeRelated(row.original).protocol}</span>
        ),
      },
      {
        id: 'endpoints',
        header: 'Between',
        cell: ({ row }) => {
          const line = describeRelated(row.original)
          return (
            <span className="break-all">
              {line.from} → {line.to}
            </span>
          )
        },
      },
      {
        id: 'size',
        header: 'Size and risk',
        cell: ({ row }) => {
          const line = describeRelated(row.original)
          return (
            <span className="text-muted text-xs whitespace-nowrap">
              {line.size} · risk {line.risk}
            </span>
          )
        },
      },
    ],
    [],
  )

  const table = useTable({ features, columns, data: rows })

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
      <table
        aria-label="Related sessions"
        className="border-border w-full rounded-lg border text-sm"
      >
        <thead className="sr-only">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id} scope="col">
                  <table.FlexRender header={header} />
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className="divide-border divide-y">
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="hover:bg-accent/5">
              {row.getAllCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2">
                  <table.FlexRender cell={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

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
