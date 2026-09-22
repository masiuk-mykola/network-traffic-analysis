import { describe, expect, it } from 'vitest'

import { mergeDetections, RING_SIZE, type Detection } from './merge'

const at = (seq: number): Detection =>
  ({ seq, id: `d${seq}`, session_id: '72075232438042624' }) as unknown as Detection

describe('mergeDetections', () => {
  it('puts the newest first', () => {
    expect(mergeDetections([], [at(1), at(3), at(2)]).map((d) => d.seq)).toEqual([3, 2, 1])
  })

  it('shows a detection once, however many times it arrives', () => {
    // The ring is replayed on every resume, so the overlap with what is already on screen is the
    // normal case, not an anomaly.
    const held = mergeDetections([], [at(1), at(2)])

    expect(mergeDetections(held, [at(2), at(3)]).map((d) => d.seq)).toEqual([3, 2, 1])
  })

  it('keeps what it already had when nothing new arrives', () => {
    const held = mergeDetections([], [at(5)])

    expect(mergeDetections(held, [])).toEqual(held)
  })

  it('does not grow past what the server itself keeps', () => {
    const many = Array.from({ length: RING_SIZE + 250 }, (_, index) => at(index + 1))

    const merged = mergeDetections([], many)

    expect(merged).toHaveLength(RING_SIZE)
    expect(merged[0]?.seq).toBe(RING_SIZE + 250)
  })

  it('drops the oldest, not the newest, when it overflows', () => {
    const held = mergeDetections(
      [],
      Array.from({ length: RING_SIZE }, (_, index) => at(index + 1)),
    )

    const merged = mergeDetections(held, [at(RING_SIZE + 1)])

    expect(merged[0]?.seq).toBe(RING_SIZE + 1)
    expect(merged.at(-1)?.seq).toBe(2)
  })

  it('leaves the list it was given alone', () => {
    const held = mergeDetections([], [at(1)])
    const before = [...held]

    mergeDetections(held, [at(2)])

    expect(held).toEqual(before)
  })
})
