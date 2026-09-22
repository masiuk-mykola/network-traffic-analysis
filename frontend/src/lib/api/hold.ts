import 'server-only'

import { ApiError } from './client'

/**
 * One answer, held for a while, read once at a time.
 *
 * Some reads are the same for everyone and change on the scale of a deploy: the field catalogue, the
 * server's own condition. Asking for them per render is wasteful in production and actively scored
 * against us — the API counts identical reads and, when one is refused with a delay attached, counts
 * the next one as a retry. A render that happens twice would violate a delay it never saw.
 *
 * So: the answer is kept for `windowMs`, and while one read is in flight every other caller waits
 * for it rather than starting a second.
 */
type Held<T> = { at: number; value: T }

/** A refusal that named a delay, kept until that delay has passed. */
type Refused = { until: number; error: unknown }

type Slot<T> = { held?: Held<T>; refused?: Refused; inFlight?: Promise<T> }

const slots = globalThis as typeof globalThis & { __captureHolds?: Map<string, Slot<unknown>> }

export async function holdRead<T>(key: string, windowMs: number, read: () => Promise<T>) {
  slots.__captureHolds ??= new Map()
  const slot = (slots.__captureHolds.get(key) ?? {}) as Slot<T>
  slots.__captureHolds.set(key, slot as Slot<unknown>)

  const held = slot.held
  if (held && Date.now() - held.at < windowMs) return held.value

  // A refusal that asked us to wait is re-thrown rather than re-asked: the next render is a second
  // reader, and the API counts its read as a retry made before the delay it advertised.
  const refused = slot.refused
  if (refused && Date.now() < refused.until) throw refused.error
  slot.refused = undefined

  slot.inFlight ??= read()
    .then((value) => {
      slot.held = { at: Date.now(), value }
      return value
    })
    .catch((error: unknown) => {
      const wait = advertisedWait(error)
      if (wait !== null) slot.refused = { until: Date.now() + wait, error }
      throw error
    })
    .finally(() => {
      slot.inFlight = undefined
    })

  return slot.inFlight
}

/** How long a refusal asked us to wait, or null when it asked for nothing. */
function advertisedWait(error: unknown): number | null {
  if (!(error instanceof ApiError)) return null
  return error.retryAfterMs !== null && error.retryAfterMs > 0 ? error.retryAfterMs : null
}
