import { formatByteCount, formatBytes, type ByteCount } from './bytes'
import { formatDuration } from './duration'
import { EMPTY } from './empty'
import { formatEndpoint, type Endpoint } from './endpoint'
import { formatTimestamp } from './time'

/**
 * The API names the kind of every column it publishes and tells us to render anything else as text.
 * This is that mapping, in one place, so two screens cannot disagree about what a duration looks like.
 */
export function formatByColumnType(type: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return EMPTY

  const asCount = asNumber(value)

  switch (type) {
    case 'ts':
      return typeof value === 'string' ? formatTimestamp(value) : asText(value)
    // A table column carries both directions; a decoded field carries a single size, and an older
    // decoder quotes it as a string.
    case 'bytes':
      if (isByteCount(value)) return formatByteCount(value).total
      return asCount === null ? asText(value) : formatBytes(asCount)
    case 'duration':
    case 'duration_ms':
      return asCount === null ? asText(value) : formatDuration(asCount)
    case 'ip_port':
      return isEndpoint(value) ? formatEndpoint(value).address : asText(value)
    case 'risk':
      return isRisk(value) ? `${value.score} (${value.band})` : asText(value)
    // An identifier is wider than a JavaScript number: it is passed through untouched, never parsed.
    case 'id':
      return typeof value === 'string' ? value : asText(value)
    default:
      return asText(value)
  }
}

/** The older decoder quotes numbers as strings; a value that is not one at all stays text. */
function asNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string' || value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function asText(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value) ?? EMPTY
}

function isByteCount(value: unknown): value is ByteCount {
  return isRecord(value) && typeof value.up === 'number' && typeof value.down === 'number'
}

function isEndpoint(value: unknown): value is Endpoint {
  return isRecord(value) && typeof value.ip === 'string' && typeof value.port === 'number'
}

function isRisk(value: unknown): value is { score: number; band: string } {
  return isRecord(value) && typeof value.score === 'number' && typeof value.band === 'string'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}
