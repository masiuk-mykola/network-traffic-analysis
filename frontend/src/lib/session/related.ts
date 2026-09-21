import type { components } from '@api/schema'
import { formatByteCount, formatTimestamp } from '@lib/format'

export type RelatedRow = components['schemas']['SessionRow']
export type RelatedWindow = components['schemas']['RelatedWindow']

/** The only windows the server accepts; anything else is refused outright. */
export const RELATED_WINDOWS: ReadonlyArray<{ value: RelatedWindow; label: string }> = [
  { value: '15m', label: '15 min' },
  { value: '1h', label: '1 hour' },
  { value: '6h', label: '6 hours' },
]

export type RelatedLine = {
  href: string
  when: string
  protocol: string
  from: string
  to: string
  size: string
  risk: string
}

/**
 * One line of the list, out of the row the server already sends. The server does not say why it
 * considers two sessions related, so nothing here claims a reason.
 */
export function describeRelated(row: RelatedRow): RelatedLine {
  return {
    // The id is a uint64 as a string: it goes into the address exactly as it arrived.
    href: `/sessions/${row.id}`,
    when: formatTimestamp(row.start),
    protocol: row.protocol,
    from: endpoint(row.src),
    to: endpoint(row.dst),
    size: formatByteCount(row.bytes).total,
    risk: `${row.risk.score} (${row.risk.band})`,
  }
}

/** A host name where the capture resolved one, the address where it did not. */
function endpoint(value: RelatedRow['src']): string {
  return `${value.host ?? value.ip}:${value.port}`
}
