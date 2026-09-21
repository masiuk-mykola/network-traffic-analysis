import type { components } from '@api/schema'
import { EMPTY, formatByColumnType } from '@lib/format'

type SessionRow = components['schemas']['SessionRow']
type Column = { key: string; type: string }

/**
 * A published column key names something to show, not a field on the row: `sensor` is the row's
 * sensor id, `files` its file count, `dst_country` a property of its destination. This is that map,
 * and a key it has never seen is an empty cell rather than a crash.
 */
const READERS: Record<string, (row: SessionRow) => unknown> = {
  start: (row) => row.start,
  end: (row) => row.end,
  sensor: (row) => row.sensor_id,
  src: (row) => row.src,
  dst: (row) => row.dst,
  protocol: (row) => row.protocol,
  transport: (row) => row.transport,
  summary: (row) => row.summary,
  bytes: (row) => row.bytes,
  duration: (row) => row.duration_ms,
  risk: (row) => row.risk,
  id: (row) => row.id,
  packets: (row) => totalOf(row.packets),
  decoder: (row) => row.decoder,
  files: (row) => row.files_count,
  dst_country: (row) => row.dst.country,
}

export function rowValue(row: SessionRow, column: Column): string {
  const read = READERS[column.key]
  if (!read) return EMPTY

  return formatByColumnType(column.type, read(row))
}

function totalOf(count: { up: number; down: number } | undefined): number | null {
  return count ? count.up + count.down : null
}
