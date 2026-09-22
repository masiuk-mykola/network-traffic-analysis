import type { components } from '@api/schema'

export type Detection = components['schemas']['Detection']

/**
 * What the server itself keeps. Holding more than the ring would be holding detections the server
 * can no longer replay, which is a list that only grows.
 */
export const RING_SIZE = 1_000

/**
 * The detections on screen, newest first.
 *
 * Arrivals overlap with what is already held: every resume replays the ring from the point given,
 * so the same detection is delivered again on purpose. `seq` is the server's own order and its
 * identity, so it is both the sort and the de-duplication.
 */
export function mergeDetections(
  held: readonly Detection[],
  arriving: readonly Detection[],
): Detection[] {
  if (arriving.length === 0) return held as Detection[]

  const bySeq = new Map<number, Detection>()
  for (const detection of held) bySeq.set(detection.seq, detection)
  for (const detection of arriving) bySeq.set(detection.seq, detection)

  return [...bySeq.values()].sort((a, b) => b.seq - a.seq).slice(0, RING_SIZE)
}
