import 'server-only'

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

type Slot<T> = { held?: Held<T>; inFlight?: Promise<T> }

const slots = globalThis as typeof globalThis & { __captureHolds?: Map<string, Slot<unknown>> }

export async function holdRead<T>(key: string, windowMs: number, read: () => Promise<T>) {
  slots.__captureHolds ??= new Map()
  const slot = (slots.__captureHolds.get(key) ?? {}) as Slot<T>
  slots.__captureHolds.set(key, slot as Slot<unknown>)

  const held = slot.held
  if (held && Date.now() - held.at < windowMs) return held.value

  slot.inFlight ??= read()
    .then((value) => {
      slot.held = { at: Date.now(), value }
      return value
    })
    .finally(() => {
      slot.inFlight = undefined
    })

  return slot.inFlight
}
