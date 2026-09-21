import { EMPTY } from './empty'

const SECOND_MS = 1000
const MINUTE_MS = 60 * SECOND_MS
const HOUR_MS = 60 * MINUTE_MS

/**
 * Full precision below a second — the question here is often whether two sessions overlapped —
 * and readable units above it.
 */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return EMPTY
  if (ms < SECOND_MS) return `${Math.round(ms)} ms`
  if (ms < MINUTE_MS) return `${(ms / SECOND_MS).toFixed(1)} s`

  if (ms < HOUR_MS) {
    const minutes = Math.floor(ms / MINUTE_MS)
    const seconds = Math.floor((ms % MINUTE_MS) / SECOND_MS)
    return `${minutes} m ${pad(seconds)} s`
  }

  const hours = Math.floor(ms / HOUR_MS)
  const minutes = Math.floor((ms % HOUR_MS) / MINUTE_MS)
  return `${hours} h ${pad(minutes)} m`
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}
