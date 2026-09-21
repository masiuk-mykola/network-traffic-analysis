import { EMPTY } from './empty'

/**
 * Everything is shown in UTC, with the zone spelled out. The API answers in UTC, but each capture
 * point also publishes its own zone and one legacy field is a local string in a different format —
 * mixing them would make a timeline wrong in a way nobody notices. Formatting from the UTC parts of
 * the date rather than through `Intl` also keeps the output identical on every machine.
 */
export function formatTimestamp(iso: string | null | undefined): string {
  const date = parse(iso)
  if (!date) return fallback(iso)

  return `${datePart(date)} ${timePart(date)} UTC`
}

/** For a dense table cell, where the date is already established by the column or the filter. */
export function formatTimeOfDay(iso: string | null | undefined): string {
  const date = parse(iso)
  if (!date) return fallback(iso)

  return timePart(date)
}

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

function fallback(iso: string | null | undefined): string {
  return iso ? iso : EMPTY
}

function datePart(date: Date): string {
  const year = date.getUTCFullYear()
  const month = pad(date.getUTCMonth() + 1)
  const day = pad(date.getUTCDate())
  return `${year}-${month}-${day}`
}

function timePart(date: Date): string {
  const hours = pad(date.getUTCHours())
  const minutes = pad(date.getUTCMinutes())
  const seconds = pad(date.getUTCSeconds())
  const millis = String(date.getUTCMilliseconds()).padStart(3, '0')
  return `${hours}:${minutes}:${seconds}.${millis}`
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}
