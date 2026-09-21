import { EMPTY } from './empty'

const UNITS = ['B', 'kB', 'MB', 'GB', 'TB'] as const
const STEP = 1000

/** Traffic volumes are quoted in SI units on the wire, so 1 kB is 1000 B here. */
export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return EMPTY
  if (value < STEP) return `${Math.round(value)} B`

  let scaled = value
  let unit = 0
  while (scaled >= STEP && unit < UNITS.length - 1) {
    scaled /= STEP
    unit += 1
  }
  return `${scaled.toFixed(1)} ${UNITS[unit]}`
}

export type ByteCount = { up: number; down: number }

export type FormattedByteCount = { total: string; up: string; down: string }

/** The table shows the total and both directions, so it never has to add them up itself. */
export function formatByteCount(value: ByteCount | null | undefined): FormattedByteCount {
  if (!value) return { total: EMPTY, up: EMPTY, down: EMPTY }
  return {
    total: formatBytes(value.up + value.down),
    up: formatBytes(value.up),
    down: formatBytes(value.down),
  }
}
