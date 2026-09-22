'use client'

import { Radio } from 'lucide-react'
import Link from 'next/link'

import { useDetections, type Feed } from '@lib/detections/use-detections'
import type { Detection } from '@lib/detections/merge'
import type { FeedStatus } from '@lib/detections/upstream-events'
import { formatEndpoint } from '@lib/format/endpoint'
import { formatTimestamp } from '@lib/format/time'
import { ROUTES } from '@lib/routes'
import { cn } from '@lib/utils'
import { EmptyState, ErrorState, LoadingState } from '@/components/states'

export function DetectionFeed() {
  const { detections, status, restarted, seed } = useDetections()

  if (seed.isPending) return <LoadingState label="Loading detections" />

  // A refused seed costs the seed, not the screen: the live connection is a separate read and may
  // well be delivering. So the failure is reported where the older detections would have been, and
  // the feed above it keeps saying what it is doing.
  const seedFailed = Boolean(seed.error) && detections.length === 0

  return (
    <section aria-label="Detections" className="flex flex-col gap-3">
      <Connection status={status} count={detections.length} />

      {restarted ? (
        <p className="border-border text-muted rounded-lg border border-dashed px-3 py-2 text-sm">
          The feed restarted: this session was away longer than the server keeps detections, so what
          came in between is not here.
        </p>
      ) : null}

      <Body failed={seedFailed} detections={detections} seed={seed} />
    </section>
  )
}

function Body({
  failed,
  detections,
  seed,
}: {
  failed: boolean
  detections: Detection[]
  seed: Feed['seed']
}) {
  if (failed) {
    return <ErrorState error={seed.error} onRetry={seed.refetch} retrying={seed.isFetching} />
  }

  if (detections.length === 0) {
    return (
      <EmptyState
        icon={Radio}
        title="Nothing flagged yet"
        description="The feed is open. Detections appear here as the capture points raise them."
      />
    )
  }

  return (
    <ol className="flex flex-col gap-2">
      {detections.map((detection) => (
        <li key={detection.seq}>
          <DetectionRow detection={detection} />
        </li>
      ))}
    </ol>
  )
}

/**
 * The connection's own condition, kept apart from the list and announced politely: a screenful of
 * rows must not be read aloud again every time one arrives.
 */
function Connection({ status, count }: { status: FeedStatus; count: number }) {
  const label: Record<FeedStatus, string> = {
    live: 'Live',
    reconnecting: 'Reconnecting',
    stopped: 'Stopped',
  }
  const tone: Record<FeedStatus, string> = {
    live: 'bg-accent',
    reconnecting: 'bg-warning',
    stopped: 'bg-muted',
  }

  return (
    <div className="text-muted flex items-center gap-2 text-xs">
      <span aria-hidden className={cn('size-2 rounded-full', tone[status])} />
      <span>{label[status]}</span>
      <span aria-live="polite" className="sr-only">
        {`Feed ${label[status].toLowerCase()}, ${count} detections`}
      </span>
    </div>
  )
}

function DetectionRow({ detection }: { detection: Detection }) {
  const src = formatEndpoint(detection.src)
  const dst = formatEndpoint(detection.dst)

  return (
    <Link
      // The session id is a uint64 as a string; it goes into the address exactly as it arrived.
      href={ROUTES.session(detection.session_id)}
      className="border-border bg-surface/40 hover:bg-accent/5 focus-visible:ring-ring/60 block rounded-lg border p-3 focus-visible:ring-2 focus-visible:outline-none"
    >
      <div className="flex items-baseline gap-2">
        <Severity value={detection.severity} />
        <span className="text-muted font-mono text-xs">{formatTimestamp(detection.ts)}</span>
        <span className="truncate font-medium">{detection.rule}</span>
      </div>
      <p className="text-muted mt-1 truncate font-mono text-xs">
        {`${detection.sensor_id} · ${src.address} → ${dst.address}`}
      </p>
      <p className="text-muted mt-0.5 truncate text-xs">
        {`${detection.mitre.technique_id} · ${detection.mitre.name}`}
      </p>
    </Link>
  )
}

function Severity({ value }: { value: Detection['severity'] }) {
  const tone: Record<string, string> = {
    high: 'border-danger/40 text-danger',
    medium: 'border-warning/40 text-warning',
    low: 'border-border text-muted',
  }

  return (
    <span
      className={cn(
        'rounded-full border px-2 py-0.5 font-mono text-[0.65rem] tracking-wider uppercase',
        tone[value] ?? tone.low,
      )}
    >
      {value}
    </span>
  )
}
