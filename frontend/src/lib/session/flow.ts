import type { components } from '@api/schema'

export type FlowSample = components['schemas']['FlowSample']
export type FlowMetric = 'bytes' | 'packets'

/** The width the server accepts, either end inclusive; anything outside is refused. */
export const MIN_BUCKET_MS = 100
export const MAX_BUCKET_MS = 60_000

const LADDER = [100, 250, 500, 1_000, 5_000, 15_000, MAX_BUCKET_MS]
/** Fewer than this many columns is not a shape; more than this is a smear. */
const FEWEST = 2
const MOST = 200
/** What a readable timeline looks like, used to pick the width to start with. */
const COMFORTABLE = 40
const MOST_CHOICES = 4

export type FlowColumn = {
  /** Bucket start, epoch milliseconds — the column's position comes from this, never from its index. */
  t: number
  up: number
  down: number
  /** Where the column sits across the series, 0 to 1, and how wide it is on the same scale. */
  offset: number
  width: number
}

export type FlowSeries = {
  columns: FlowColumn[]
  /** The largest value in either direction; both halves are drawn against it. */
  peak: number
  totals: { up: number; down: number }
}

/**
 * The widths worth offering for a session of this length: every one inside the range the server
 * accepts, so a refused width is impossible, and each producing a picture that can be read.
 */
export function bucketChoices(durationMs: number): number[] {
  const fitting = LADDER.filter((width) => {
    const columns = Math.ceil(Math.max(durationMs, 1) / width)
    return columns >= FEWEST && columns <= MOST
  })

  if (fitting.length === 0) {
    // Shorter than one bucket, or longer than the coarsest the server serves.
    return [durationMs < LADDER[0]! * FEWEST ? MIN_BUCKET_MS : MAX_BUCKET_MS]
  }

  return fitting.slice(0, MOST_CHOICES)
}

/** The width to start with: the offered one that lands closest to a comfortable column count. */
export function defaultBucket(durationMs: number): number {
  const choices = bucketChoices(durationMs)

  return choices.reduce((best, width) => {
    const distance = (candidate: number) =>
      Math.abs(Math.ceil(Math.max(durationMs, 1) / candidate) - COMFORTABLE)
    return distance(width) < distance(best) ? width : best
  }, choices[0]!)
}

/**
 * Samples turned into columns that know when they are.
 *
 * The server omits a bucket in which nothing happened, so consecutive samples are not consecutive
 * moments. Each column therefore carries its own position across the series, and the renderer leaves
 * the space between two samples empty instead of closing the ranks.
 */
export function toSeries(
  samples: readonly FlowSample[],
  bucketMs: number,
  metric: FlowMetric,
): FlowSeries {
  if (samples.length === 0) return { columns: [], peak: 0, totals: { up: 0, down: 0 } }

  const ordered = [...samples].sort((a, b) => a.t - b.t)
  const start = ordered[0]!.t
  const end = ordered.at(-1)!.t + bucketMs
  const span = Math.max(end - start, bucketMs)

  const columns = ordered.map((item) => ({
    t: item.t,
    up: metric === 'bytes' ? item.bytes_up : item.packets_up,
    down: metric === 'bytes' ? item.bytes_down : item.packets_down,
    offset: (item.t - start) / span,
    width: bucketMs / span,
  }))

  return {
    columns,
    peak: columns.reduce((most, column) => Math.max(most, column.up, column.down), 0),
    totals: {
      up: columns.reduce((sum, column) => sum + column.up, 0),
      down: columns.reduce((sum, column) => sum + column.down, 0),
    },
  }
}
