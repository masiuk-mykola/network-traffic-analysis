'use client'

import { tableFeatures, useTable, type ColumnDef as TableColumnDef } from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp } from 'lucide-react'
import Link from 'next/link'
import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'

import type { components } from '@api/schema'
import { formatCount } from '@lib/format'
import { ROUTES } from '@lib/routes'
import { rowValue } from '@lib/search/row-value'
import { isGone, isRunning, type SearchStatus } from '@lib/search/search-state'
import { directionOf, sortFieldFor, toggleSort, type SortKey } from '@lib/search/sort'
import { useColumns, type ColumnDef } from '@lib/search/use-columns'
import { useResults } from '@lib/search/use-results'
import { cn } from '@lib/utils'
import { EmptyState, ErrorState, LoadingState } from '@/components/states'
import { Button } from '@/components/ui'

type SessionRow = components['schemas']['SessionRow']

/** One number for the measurement and the style; two would make the scrollbar lie. */
const ROW_HEIGHT = 36
const OVERSCAN = 8
/** How close to the end of the loaded rows before the next page is asked for. */
const LOAD_AHEAD = 12
const SCROLLER_HEIGHT = 448

/**
 * Sorting and paging are the server's, and the address bar is where the order lives, so none of the
 * row-model features are turned on: they would hold a second copy of a state this screen does not
 * own. The table is used for what it does own here — the column model built from `/v1/meta/columns`
 * and the rendering of headers and cells.
 */
const features = tableFeatures({})

const EMPTY_ROWS: SessionRow[] = []

export function ResultsTable({
  searchId,
  status,
  sort,
  onSortChange,
}: {
  searchId: string | null
  status: SearchStatus | undefined
  sort: SortKey
  onSortChange: (sort: SortKey) => void
}) {
  const running = status ? isRunning(status) : false
  const gone = status ? isGone(status) : false
  // Rows are read only once the job has answered for itself: asking about one the server does not
  // have earns a 404, and a 404 asked twice is scored against us.
  const known = status !== undefined && !gone
  const columns = useColumns()
  const results = useResults(known ? searchId : null, running, sort)
  const scroller = useRef<HTMLDivElement>(null)

  // Both of these are read by every rendered row, so they are kept stable: a fresh array each
  // render would re-render the whole window on any parent change.
  const published = columns.data
  const visible = useMemo(
    () => (published ?? []).filter((column) => column.default_visible),
    [published],
  )
  const pages = results.data?.pages
  const rows = useMemo(() => pages?.flatMap((page) => page.items) ?? EMPTY_ROWS, [pages])

  const tableColumns = useMemo<TableColumnDef<typeof features, SessionRow>[]>(
    () =>
      visible.map((column) => ({
        id: column.key,
        header: column.label,
        // A published key names something to show, not a field on the row; `rowValue` is that map.
        cell: ({ row }) => rowValue(row.original, column),
      })),
    [visible],
  )

  const table = useTable({ features, columns: tableColumns, data: rows })

  const complete = results.data?.pages.at(-1)?.complete ?? false
  const modelRows = table.getRowModel().rows

  const virtual = useVirtualizer({
    count: modelRows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    getItemKey: (index) => modelRows[index]?.id ?? index,
    overscan: OVERSCAN,
    // Used until the scroller can be measured, which is also the case in an environment with no
    // layout at all; without it the window would be empty rather than merely approximate.
    initialRect: { width: 1024, height: SCROLLER_HEIGHT },
  })

  // Rows are interactive and there are a hundred thousand of them, so the table carries one tab
  // stop and the arrows move it. Tabbing through every loaded row instead would be a trap.
  const [focused, setFocused] = useState(0)
  const takeFocus = useRef(false)

  const moveFocus = useCallback(
    (next: number) => {
      const last = rows.length - 1
      const clamped = Math.min(Math.max(next, 0), last)
      takeFocus.current = true
      setFocused(clamped)
      // The row may be outside the window, and an unmounted row cannot be focused.
      virtual.scrollToIndex(clamped)
    },
    [rows.length, virtual],
  )

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      const moves: Record<string, number | undefined> = {
        ArrowDown: focused + 1,
        ArrowUp: focused - 1,
        Home: 0,
        End: rows.length - 1,
      }
      const next = moves[event.key]
      if (next === undefined) return
      event.preventDefault()
      moveFocus(next)
    },
    [focused, moveFocus, rows.length],
  )

  // Focus follows the roving index, but only when a key moved it: stealing focus on a re-render
  // would pull it out of the form above while a search is still filling the table.
  useEffect(() => {
    if (!takeFocus.current) return
    takeFocus.current = false
    const element = scroller.current?.querySelector<HTMLElement>(`[data-row-index="${focused}"]`)
    element?.focus()
  })

  // Asking for the next page is a side effect, so it belongs in an effect: doing it while
  // rendering fires twice in development and can ask for the same cursor more than once.
  const lastVisible = virtual.getVirtualItems().at(-1)?.index ?? -1
  const nearEnd = lastVisible >= rows.length - LOAD_AHEAD
  const canLoadMore = results.hasNextPage && !results.isFetchingNextPage

  useEffect(() => {
    if (nearEnd && canLoadMore) void results.fetchNextPage()
  }, [nearEnd, canLoadMore, results])

  // A job the server does not have has no rows to show; the progress panel explains it instead.
  if (!searchId || gone) return null
  if (columns.isPending || results.isPending) return <LoadingState label="Loading results" />
  if (columns.isError) {
    return <ErrorState error={columns.error} onRetry={() => void columns.refetch()} />
  }
  if (results.isError && rows.length === 0) {
    return <ErrorState error={results.error} onRetry={() => void results.refetch()} />
  }

  if (rows.length === 0) {
    return running ? (
      <LoadingState label="Still looking — no sessions have matched yet" />
    ) : (
      <EmptyState
        title="No sessions matched"
        description="Nothing in this window matched the conditions. Widen the window, or drop a condition."
      />
    )
  }

  return (
    <section className="space-y-2">
      <div className="text-muted flex items-baseline justify-between text-xs">
        <p>{formatCount(rows.length)} loaded</p>
        {running ? <p>More may still arrive.</p> : null}
      </div>

      <div className="border-border overflow-hidden rounded-lg border">
        <div
          role="grid"
          aria-label="Results"
          aria-rowcount={rows.length}
          onKeyDown={onKeyDown}
          className="w-full overflow-x-auto text-sm"
          style={{ minWidth: 'min-content' }}
        >
          {table.getHeaderGroups().map((group) => (
            <div
              key={group.id}
              role="row"
              className="border-border bg-surface/60 flex border-b font-medium"
            >
              {group.headers.map((header) => (
                <HeaderCell
                  key={header.id}
                  column={byId(visible, header.column.id)}
                  running={running}
                  sort={sort}
                  onSortChange={onSortChange}
                />
              ))}
            </div>
          ))}

          <div ref={scroller} className="overflow-y-auto" style={{ height: SCROLLER_HEIGHT }}>
            <div style={{ height: virtual.getTotalSize(), position: 'relative' }}>
              {virtual.getVirtualItems().map((item) => {
                const row = modelRows[item.index]
                if (!row) return null
                return (
                  <Row
                    key={row.id}
                    row={row.original}
                    columns={visible}
                    top={item.start}
                    index={item.index}
                    focused={item.index === focused}
                  />
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {results.isError ? (
        <ErrorState error={results.error} onRetry={results.retry} className="min-h-0 py-2" />
      ) : null}

      {complete ? (
        <p className="text-muted text-xs">That is every session this search matched.</p>
      ) : results.hasNextPage ? (
        <Button
          variant="secondary"
          size="sm"
          disabled={results.isFetchingNextPage}
          onClick={() => void results.fetchNextPage()}
        >
          {results.isFetchingNextPage ? 'Loading more' : 'Load more'}
        </Button>
      ) : null}
    </section>
  )
}

/** The table knows the column by its id; the width and what may be sorted are the server's own. */
function byId(columns: ColumnDef[], id: string): ColumnDef {
  const found = columns.find((column) => column.key === id)
  if (!found) throw new Error(`No published column named ${id}`)
  return found
}

const HeaderCell = memo(function HeaderCell({
  column,
  running,
  sort,
  onSortChange,
}: {
  column: ColumnDef
  running: boolean
  sort: SortKey
  onSortChange: (sort: SortKey) => void
}) {
  // The server publishes what may be sorted; we can only send it an order it named.
  const sortable = column.sortable && sortFieldFor(column.key) !== null
  const direction = sortable ? directionOf(sort, column.key) : null

  const onClick = useCallback(
    () => onSortChange(toggleSort(sort, column.key)),
    [onSortChange, sort, column.key],
  )

  const label = (
    <span className="truncate" style={{ width: column.width_hint }}>
      {column.label}
    </span>
  )

  return (
    <div role="columnheader" aria-sort={direction ?? undefined} className="shrink-0 px-3 py-2">
      {sortable ? (
        <button
          type="button"
          disabled={running}
          title={running ? 'A different order needs a finished search' : undefined}
          onClick={onClick}
          className={cn(
            'flex w-full items-center gap-1 text-left',
            'hover:text-accent disabled:cursor-not-allowed disabled:opacity-60',
            direction && 'text-accent',
          )}
        >
          {label}
          {direction === 'descending' ? (
            <ArrowDown aria-hidden className="size-3 shrink-0" />
          ) : null}
          {direction === 'ascending' ? <ArrowUp aria-hidden className="size-3 shrink-0" /> : null}
        </button>
      ) : (
        label
      )}
    </div>
  )
})

const Row = memo(function Row({
  row,
  columns,
  top,
  index,
  focused,
}: {
  row: SessionRow
  columns: ColumnDef[]
  top: number
  index: number
  /** The one row holding the table's tab stop. */
  focused: boolean
}) {
  return (
    <Link
      role="row"
      aria-rowindex={index + 1}
      data-row-index={index}
      tabIndex={focused ? 0 : -1}
      href={ROUTES.session(row.id)}
      className={cn(
        'border-border hover:bg-accent/5 focus-visible:ring-ring/50 absolute flex w-full border-b',
        'focus-visible:ring-2 focus-visible:outline-none',
      )}
      style={{ height: ROW_HEIGHT, transform: `translateY(${top}px)` }}
    >
      {columns.map((column) => (
        <div
          key={column.key}
          role="gridcell"
          className="truncate px-3 py-2"
          style={{ width: column.width_hint, flexShrink: 0 }}
        >
          {rowValue(row, column)}
        </div>
      ))}
    </Link>
  )
})
