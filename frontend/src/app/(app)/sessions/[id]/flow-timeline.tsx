'use client'

import { tableFeatures, useTable, type ColumnDef as TableColumnDef } from '@tanstack/react-table'
import { useMemo, useState } from 'react'

import { formatBytes, formatCount, formatTimeOfDay } from '@lib/format'
import {
  bucketChoices,
  defaultBucket,
  toSeries,
  type FlowColumn,
  type FlowMetric,
  type FlowSeries,
} from '@lib/session/flow'
import { useFlow } from '@lib/session/use-flow'
import { cn } from '@lib/utils'
import { EmptyState, ErrorState, LoadingState } from '@/components/states'
import { Button } from '@/components/ui'

const features = tableFeatures({})

/** Half the plot belongs to each direction, so a column never crosses the baseline. */
const HALF_HEIGHT = 44

/**
 * How the traffic moved while the session was open. The server sums it into buckets and omits the
 * empty ones, so a quiet stretch has to read as quiet: each column is placed at its own moment
 * rather than next to its neighbour.
 */
export function FlowTimeline({ sessionId, durationMs }: { sessionId: string; durationMs: number }) {
  const choices = bucketChoices(durationMs)
  const [bucketMs, setBucketMs] = useState(() => defaultBucket(durationMs))
  const [metric, setMetric] = useState<FlowMetric>('bytes')
  const flow = useFlow(sessionId, bucketMs)

  const heading = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-muted text-xs tracking-wide uppercase">Traffic over time</p>
      <div className="flex items-center gap-1">
        {(['bytes', 'packets'] as const).map((option) => (
          <Button
            key={option}
            variant={metric === option ? 'secondary' : 'ghost'}
            size="sm"
            aria-pressed={metric === option}
            onClick={() => setMetric(option)}
          >
            {option}
          </Button>
        ))}
        {choices.length > 1
          ? choices.map((width) => (
              <Button
                key={width}
                variant={bucketMs === width ? 'secondary' : 'ghost'}
                size="sm"
                aria-pressed={bucketMs === width}
                onClick={() => setBucketMs(width)}
              >
                {labelFor(width)}
              </Button>
            ))
          : null}
      </div>
    </div>
  )

  return (
    <section aria-label="Traffic over time" className="space-y-3">
      {heading}
      <Body
        durationMs={durationMs}
        metric={metric}
        flow={flow}
        onRetry={() => void flow.refetch()}
      />
    </section>
  )
}

function Body({
  durationMs,
  metric,
  flow,
  onRetry,
}: {
  durationMs: number
  metric: FlowMetric
  flow: ReturnType<typeof useFlow>
  onRetry: () => void
}) {
  if (flow.isPending) return <LoadingState label="Reading the traffic" className="min-h-24" />
  if (flow.isError) {
    return (
      <ErrorState
        error={flow.error}
        onRetry={onRetry}
        retrying={flow.isFetching}
        className="min-h-0 py-2"
      />
    )
  }

  // The server reports the width it applied; everything shown is labelled with that, not with what
  // was asked for.
  const bucketMs = flow.data.bucket_ms
  const series = toSeries(flow.data.samples, bucketMs, metric)

  if (series.columns.length === 0) {
    return (
      <EmptyState
        title="No traffic was recorded over time"
        description="The capture has no per-moment numbers for this session."
      />
    )
  }

  if (series.columns.length === 1) {
    return (
      <div className="space-y-2">
        <p className="text-muted text-sm">
          This session lasted {formatCount(durationMs)} ms — everything it carried falls in one
          bucket of {labelFor(bucketMs)}, so there is no shape to plot.
        </p>
        <Figures series={series} metric={metric} bucketMs={bucketMs} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <Plot series={series} />
      <p className="text-sm">
        {amount(series.totals.up, metric)} up, {amount(series.totals.down, metric)} down, in buckets
        of {labelFor(bucketMs)}
      </p>
      <Figures series={series} metric={metric} bucketMs={bucketMs} />
    </div>
  )
}

/** One scale for both directions, mirrored about the baseline, so the two stay comparable. */
function Plot({ series }: { series: FlowSeries }) {
  return (
    <div
      aria-hidden
      className="border-border bg-surface/40 relative rounded-lg border"
      style={{ height: HALF_HEIGHT * 2 + 1 }}
    >
      <div className="bg-border absolute inset-x-0 top-1/2 h-px" />
      {series.columns.map((column) => (
        <div
          key={column.t}
          className="absolute top-0 bottom-0"
          style={{
            left: `${column.offset * 100}%`,
            width: `max(2px, ${column.width * 100}%)`,
          }}
        >
          <div
            className="bg-accent/80 absolute bottom-1/2 w-full rounded-t-sm"
            style={{ height: bar(column.up, series.peak) }}
          />
          <div
            className={cn('absolute top-1/2 w-full rounded-b-sm', 'bg-accent/35')}
            style={{ height: bar(column.down, series.peak) }}
          />
        </div>
      ))}
    </div>
  )
}

/** The picture is a picture; these are the numbers, and the keyboard can walk them. */
function Figures({
  series,
  metric,
  bucketMs,
}: {
  series: FlowSeries
  metric: FlowMetric
  bucketMs: number
}) {
  // A bucket is a row of three numbers, so the numbers behind the picture are a real table; the
  // header is for a screen reader only, because the picture above already carries the labels.
  const columns = useMemo<TableColumnDef<typeof features, FlowColumn>[]>(
    () => [
      {
        id: 'when',
        header: 'Time',
        cell: ({ row }) => (
          <span className="text-muted">
            {formatTimeOfDay(new Date(row.original.t).toISOString())}
          </span>
        ),
      },
      { id: 'up', header: 'Up', cell: ({ row }) => `${amount(row.original.up, metric)} up` },
      {
        id: 'down',
        header: 'Down',
        cell: ({ row }) => `${amount(row.original.down, metric)} down`,
      },
    ],
    [metric],
  )

  const table = useTable({ features, columns, data: series.columns })

  return (
    <details className="border-border rounded-lg border">
      <summary className="text-muted cursor-pointer px-3 py-2 text-xs">
        {formatCount(series.columns.length)} buckets of {labelFor(bucketMs)}, as numbers
      </summary>
      <div className="max-h-48 overflow-y-auto">
        <table className="w-full text-xs">
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
              <tr key={row.id} tabIndex={0} className="focus-visible:bg-accent/10">
                {row.getAllCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-1.5">
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function bar(value: number, peak: number): number {
  if (peak <= 0 || value <= 0) return 0
  return Math.max(1, Math.round((value / peak) * HALF_HEIGHT))
}

function amount(value: number, metric: FlowMetric): string {
  return metric === 'bytes' ? formatBytes(value) : `${formatCount(value)} packets`
}

function labelFor(bucketMs: number): string {
  return bucketMs >= 1_000 ? `${bucketMs / 1_000} s` : `${bucketMs} ms`
}
